"""Generate typed o32-word -> native ARM64 invocations from frontend IR.

Pointers keep guest token values: translated callees resolve their accesses.
Each mapped retail argument consumes one o32 word. The i64 frontend parameters
below are audited host longs or four-byte ModelTintColor ABI coercions, not
retail 64-bit integers. Reject new wide parameters until their ABI is audited.
"""
from llvm_guest import inspect, validate_c_abi

WIDE_WORDS = {
    'OpenEvent', 'CloseEvent', 'EnableEvent',
    'DisableEvent', 'TestEvent', 'SetRCnt', 'GetRCnt', 'StartRCnt', 'StopRCnt',
    'SetMem', 'InitPAD', 'ChangeClearPAD', 'Krom2RawAdd',
    'Model_QueueTintRequest', 'Model_QueueTintRequestForParts', 'func_80059AF8',
}
COLOR_WORDS = {'Model_QueueTintRequest', 'Model_QueueTintRequestForParts', 'func_80059AF8'}
UNSIGNED_LONG_FIRST = {'OpenEvent', 'SetRCnt', 'GetRCnt', 'StartRCnt', 'StopRCnt'}
VARIADIC_WORDS = {'Model_SetSlotProperties', 'Model_QueueTintRequestForParts', 'FntPrint'}


def signatures(texts):
    definitions, declarations = {}, {}
    for text in texts:
        for name, signature in inspect(text)['signatures'].items():
            result = signature['result']
            if result in {'i8', 'i16'} and signature['result_signext']:
                result = 's' + result[1:]
            parameters = list(signature['parameters'])
            if signature['variadic']: parameters.append({'kind': '...'})
            (definitions if signature['definition'] else declarations).setdefault(name, (result, parameters, signature))
    return {**declarations, **definitions}


def c_type(kind, name, index=None):
    if kind == 'void': return 'void'
    if kind == 'ptr': return 'void *'
    if kind == 'ptr addrspace(271)': return 'void *__ptr32'
    if kind in {'i8', 'i16', 'i32'}: return 'uint' + kind[1:] + '_t'
    if kind in {'s8', 's16'}: return 'int' + kind[1:] + '_t'
    if kind == 'i64' and (index is None or name in WIDE_WORDS): return 'uint64_t'
    raise ValueError(f'Unaudited native call type: {name} argument {index}: {kind}')


def emit_native_calls(mapped, texts, stubs=()):
    known = signatures(texts)
    output, entries = [], []
    for index, (_, name, _, _) in enumerate(sorted(mapped)):
        if name in stubs:
            ret, parameters = 'void', []
        elif name in known:
            ret, parameters, signature = known[name]
            validate_c_abi(name, signature)
        else:
            raise ValueError('Missing native call signature: ' + name)
        types, values = [], []
        for word, parameter in enumerate(parameters):
            kind = parameter['kind']
            if kind == '...':
                if name not in VARIADIC_WORDS:
                    raise ValueError('Unaudited variadic native call: ' + name)
                types.append('...')
                values.extend(f'a[{n}]' for n in range(word, 12))
                break
            if kind in {'i8', 'i16'} and parameter.get('signext'):
                kind = 's' + kind[1:]
            types.append(c_type(kind, name, word))
            if kind.startswith('ptr'):
                values.append(f'({types[-1]})(uintptr_t)a[{word}]')
            elif kind == 'i64':
                # Four-byte color structs are coerced to i64 by Apple Clang.
                signed = name not in COLOR_WORDS and not (word == 0 and name in UNSIGNED_LONG_FIRST)
                values.append(f'(uint64_t)({"int32_t" if signed else "uint32_t"})a[{word}]')
            else:
                values.append(f'({types[-1]})a[{word}]')
        if len(parameters) > 12:
            raise ValueError('Native call exceeds twelve guest words: ' + name)
        result_type = c_type(ret, name)
        call = f'(({result_type} (*)({", ".join(types) or "void"}))Memories_FunctionMap[{index}].host)({", ".join(values)})'
        expression = (call + '; return 0;' if ret == 'void' else
                      'return GuestRuntime_EncodePointer((void *)' + call + ');' if ret.startswith('ptr') else
                      'return (uint32_t)' + call + ';')
        output.append(f'static uint32_t GuestNativeCall_{index}(const uint32_t *a) {{ {expression} }}\n')
        entries.append(f'GuestNativeCall_{index}')
    output.append('static uint32_t (*const GuestNativeCalls[])(const uint32_t *) = {\n' + ',\n'.join(entries) + '\n};\n')
    output.append('uint32_t GuestRuntime_InvokeNative(unsigned index, const uint32_t *arguments) {\n'
                  '  return GuestNativeCalls[index](arguments);\n}\n')
    return ''.join(output)
