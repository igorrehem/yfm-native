# Semantic Naming Conventions

## Evidence sources

Naming decisions in this project use three different kinds of evidence:

1. `tmp/references/dotr.c` provides naming style and subsystem conventions from
   the later Yu-Gi-Oh! Duelist of the Roses codebase.
2. `tmp/references/gms.c` provides Forbidden Memories semantic analysis and
   analyst-assigned labels. Its names describe behavior but are not assumed to
   be original developer symbols.
3. `tmp/references/ram_map.txt` provides community-confirmed RAM roles, sizes,
   and gameplay context.

The games are not assumed to share implementation code. DOTR is used for style
and terminology; GenericMadScientist's IDA decompilation (`gms.c`) and the RAM
map are used for Forbidden Memories semantics.

## Function names

DOTR primarily uses a subsystem prefix followed by an underscore and a
verb-object name:

```text
SzModel_LoadMerge
SzText_LoadMerge
SzFile_DoRequest
SzData_GetConstDeck
SzSound_TransferSEGrp
SD_BGMFadeOut
SD_SEPlayOnlyOnce
RhView_SetAspect
TaHand_GetCardSummonCost
```

Use the same shape for Forbidden Memories:

```text
<Subsystem>_<Verb><Object>
```

Preferred verbs and qualifiers include:

- lifecycle: `Initialize`, `Init`, `Term`, `Reset`, `Clear`;
- access: `Get`, `Set`;
- calculation: `Calc`;
- predicates: `Is`, `Has`, `Can`, `Check`, `DoesExist`;
- resource work: `Load`, `Read`, `Free`, `Transfer`;
- control: `Play`, `Stop`, `Start`, `Update`, `Draw`;
- asynchronous work: `Req`, `Inq`, `Do`;
- callbacks: `CB`;
- per-frame work: `VSync`;
- render-pipeline variants: `_Pipe`.

Use `l<Subsystem>_...` only for a helper that is demonstrably internal to one
subsystem. Do not use the prefix merely because a function is currently called
from one place.

Names should describe observed behavior rather than guessed intent. If a
routine calculates final card attack and defense values, a name such as
`Duel_CalcCardStats` is preferable to an analyst label copied verbatim or a
speculative original name.

## Sound names

DOTR has two recognizable sound layers:

- `SzSound_...` for game-facing sound management;
- `SD_...` for the lower-level sound driver.

Related low-level families include `SDRPC_...` and `SDFS_...`. Internal sound
helpers sometimes encode the return category after the subsystem prefix, such
as `SD_iGetSDStatus` and `SD_vInitializeAutoDMA`. Preserve that form only when
the layer and return category are both supported by evidence.

The Forbidden Memories string `g_SDValue` and the DOTR symbol of the same name
support using `SD` for the sound-driver state family rather than treating `SD`
as an unknown abbreviation.

## Merge files

DOTR paths and APIs consistently use `Merge`:

```text
Merge/Icon.Mrg
Merge/Model.Mrg
Merge/Monster.Mrg
SzModel_LoadMerge
SzText_LoadMerge
```

Use `Merge` for the resource/container concept and `.Mrg` for the literal file
extension. Avoid inventing expansions such as "MRG archive" when the evidence
only establishes that these are merge files.

## Globals

DOTR generally prefixes named globals with `g` and includes the owning
subsystem:

```text
gSzView_pCamera
gSzModel_ahModel
gSzData_bRoseFlag
gSzText_apchMerge
gSzSound_sl
gRhMath_adwSinTable
```

Use:

```text
g<Subsystem>_<Role>
```

Retain a compact type prefix only when the type is established and the result
remains readable:

- `b`: byte or boolean;
- `w`: 16-bit word;
- `dw`: 32-bit word;
- `n`: integer/count/index;
- `f`: flag or floating-point value when unambiguous;
- `p`: pointer;
- `a`: array;
- doubled or combined prefixes for nested forms, such as `apch` for an array
  of character pointers.

Some sound-driver globals use the established underscore form, notably
`g_SDValue` and `g_SDBuffer`; preserve an exact cross-game name when the
semantic evidence supports it.

## Confidence policy

Every accepted semantic rename must retain:

- the original address;
- the proposed name;
- the evidence source;
- a confidence level;
- any important caveat.

Confidence levels:

- **confirmed**: direct RAM-map role, literal string/symbol evidence, or behavior
  that is uniquely established by code and callers;
- **high**: strong GMS semantics corroborated by local code, data layout, or
  multiple callers;
- **medium**: plausible analyst interpretation with useful local support but
  unresolved details;
- **deferred**: ambiguous, conflicting, or based only on an unverified analyst
  label.

Only confirmed and high-confidence names should replace address-only symbols
in the first pass. Medium-confidence proposals remain in the semantic map until
additional callers or data structures establish a stable role.
