# Yu-Gi-Oh! Forbidden Memories, a versão de PC, cria

Esse bagulho pega o **Yu-Gi-Oh! Forbidden Memories** do PlayStation 1 (o da gringa, USA)
e faz ele rodar no **Windows** de verdade. Sem emulador. Os cara decompilaram o jogo
e montaram de novo pra PC.

> **Firma isso:** o jogo **não vem junto**. Cê precisa ter a sua cópia, o arquivo `.bin`.
> Aqui só tem o código do programa.

> **Status:** ainda tá em teste, véi. O que esse projeto muda
> ([O que esse projeto muda](#o-que-esse-projeto-muda)) ainda tão olhando.

![O campo de duelo em resolução 4x](docs/screenshots/field.jpg)

---

## O que cê precisa

- Um PC com **Windows 10 ou 11 (64 bits)**.
- **Internet na primeira vez.** O programa baixa sozinho as ferramenta.
- Uns **2 GB livres** no disco.
- O arquivo **`.bin`** do **Yu-Gi-Oh! Forbidden Memories (USA)**, código **SLUS-01411**.
  - Quase sempre vem um `.cue` do lado, com o mesmo nome. Só o `.bin` que o jogo usa.
  - Versão europeia ou japonesa **não roda**. Esquece.

Cê **não** precisa instalar Python nem compilador antes. O próprio programa resolve.

---

## Como instala e joga (passo a passo)

### 1. Baixa esse projeto

Lá em cima na página do GitHub, clica no botão verde **Code** e depois em **Download ZIP**.

Antes de extrair: clica com o botão direito no ZIP, vai em **Propriedades**, marca
**Desbloquear** (se aparecer) e dá **OK**. Se não fizer isso, o Windows enche o saco depois.

Extrai numa pasta fácil de achar, tipo `C:\Jogos\yfm-native`.

> Quem mexe com Git pode só rodar
> `git clone https://github.com/Luizhsampaio/yfm-native.git`.

### 2. Joga o jogo dentro da pasta `game`

Dentro da pasta do projeto, cria uma pasta chamada **`game`** (se já não tiver)
e cola o seu **`.bin`** lá dentro. O nome do arquivo tanto faz.

Tem que ficar assim:

```
yfm-native\
   game\
      Yu-Gi-Oh! Forbidden Memories (USA).bin
   play.bat
   ...
```

### 3. Abre o jogo

Dá **dois cliques no `play.bat`**.

**A primeira vez demora** (uns 5 a 15 minutos, depende do PC e da net). Abre uma janela
preta. Nessa primeira vez o programa:

1. **Abre o seu `.bin`** e copia os arquivo do jogo pra `game\disc`
   (é rápido e só faz uma vez);
2. **Baixa as ferramenta** (fica tudo na pasta `tmp`, não instala nada no Windows);
3. **Monta o jogo** pro seu PC;
4. **Abre o jogo.**

**Nas próximas vezes** é dois cliques de novo. A janela preta pode ficar **muda, sem texto nenhum**,
por cerca de 1 minuto. Isso é o programa checando o que já tá pronto. **Não fecha essa janela.**
Se fechar, o jogo morre junto.

O jogo abre **atrás** do que cê tiver na frente (navegador, Discord, o que for).
Olha a barra de tarefas: a janela chama **Yu-Gi-Oh! Forbidden Memories**.

### 4. (Se quiser) Apaga o `.bin`

Depois que o jogo abrir a primeira vez, a pasta `game` fica com o arquivo `yfm-disc.txt`
e a pasta `disc`. Aí o **`.bin` não precisa mais** e cê pode apagar
(guarda uma cópia em outro canto, se quiser).

Não apaga e não mexe na pasta `game\disc` nem no `game\yfm-disc.txt`. É dali que o jogo lê.

---

## Controles

Dá pra jogar no **teclado** ou no **controle** (Xbox e os que prestam igual).
Dá pra trocar os botão no menu do jogo.

| PlayStation | Teclado | Controle Xbox |
|---|---|---|
| Direcionais | Setas | Direcional ou analógico esquerdo |
| ✕ (Xis), confirmar | X | A |
| ◯ (Bola), voltar | S | B |
| ▢ (Quadrado) | Z | X |
| △ (Triângulo) | A | Y |
| L1 / R1 | Q / W | LB / RB |
| L2 / R2 | E / R | LT / RT |
| Start | Enter | Menu/Start |
| Select | Shift direito | View/Back |

**Dica:** pra ver a batalha em 3D, marca o monstro que cê vai atacar e confirma com
**Quadrado (tecla Z)**, não com o Xis.

### Menu do programa

Aperta **F10** pra abrir a barra de menu. Lá tem, entre outras coisa:

- **Video > Resolution > Internal 4x**: gráfico mais nítido;
- **Video > HD text**: texto em alta;
- **Game > Mods**: liga e desliga mod;
- **Game > Language**: idioma (os idioma das versão europeia).

> O jogo pode falar que tem "versão nova". Esse aviso é do **projeto original**
> (vê [Créditos](#creditos-e-licenca)), não desse aqui. Pra desligar:
> **Help > Check for updates at start**.

---

## Saves (jogo salvo)

Os save ficam em **`Documentos\My Games\YFM Re-Decomp\saves`**.

**Trazer o save do emulador:** copia o arquivo do cartão de memória
(`.mcr`, `.mcd`, `.srm`, `.gme`, `.mcs`, `.psv`...) pra essa pasta `saves`. Depois escolhe
**LOAD** na tela inicial. (No DuckStation e no ePSXe isso fica na pasta `memcards`.)
Save state de emulador não serve. Salva dentro do jogo antes.

---

## Quando der ruim

**"O Windows protegeu o computador" (tela azul do SmartScreen)**
Clica em **Mais informações** e depois em **Executar assim mesmo**. Acontece porque o
programa foi montado no seu PC e não tem assinatura digital.

**O antivírus bloqueia o jogo / "Acesso negado"**
Antivírus, principalmente de PC de firma, bloqueia programa recém-criado.
No PC de casa, coloca a pasta do projeto como exceção. No PC da firma, fala
com o TI ou usa outro computador.

**"Put your disc image in the game folder first"**
O programa não achou o jogo. Confere:
- a pasta se chama exatamente `game` e tá **dentro** da pasta do projeto (do lado do `play.bat`);
- o arquivo lá dentro é o **`.bin`** (não o `.cue`).

**"this is not the Yu-Gi-Oh! Forbidden Memories (USA, SLUS-01411) disc"**
O `.bin` não é o da versão americana. Só o USA (SLUS-01411) funciona.

**A janela preta mostra um erro e o jogo não abre**
- Na primeira vez, vê se o PC tá na internet e roda o `play.bat` de novo.
- Se continuar, a janela fala onde ficou o relatório (pasta `tmp\pc`,
  arquivo `crash-...txt` e `last-session.log`). Abre uma issue aqui no GitHub e manda esses arquivo.

**Quero atualizar o projeto**
Baixa o ZIP novo (ou roda `git pull`) e **copia a pasta `game` antiga pra dentro**.
A pasta `game` nunca é trocada na atualização.

---

## Avisos, não vacila

- **Não manda a pasta `game` pro GitHub e não compartilha os arquivo do jogo.** É
  da Konami. O projeto já tá configurado pra o Git ignorar essa pasta (arquivo `.gitignore`);
  não apaga esse arquivo.
- Cada um usa a sua própria cópia do jogo.

---

## O que esse projeto muda

Esse repositório parte do
[Yu-Gi-Oh! Forbidden Memories Recompiled](https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled)
e quer deixar o jogo **100% nativo**:

- **Animação de ataque dos monstro em código nativo.** No projeto original, a animação de
  ataque de cada monstro (código do PlayStation guardado no `MODEL.MRG`) rodava num
  "mini emulador" embutido. Aqui elas são traduzidas sozinhas pra C na hora de montar
  o jogo (`tools/pc/model_recomp.py`).
- **O jogo roda com os arquivo aberto, sem o `.bin`.** O `.bin` é aberto uma vez só
  e os arquivo vão pra `game\disc` (`tools/pc/extract_disc.py`). Depois disso o `.bin`
  pode ser apagado.

O que vem depois, no plano: converter os arquivo do jogo pra formato comum (imagem PNG,
áudio, vídeo) e tirar a dependência do mapa de memória do PlayStation.

---

## Pra quem mexe no código

- Como o jogo é montado: [notes/pc-build.md](notes/pc-build.md)
  (tem a parte do disco extraído).
- Mods: [notes/modding.md](notes/modding.md) · FM Editor: [tools/pc/fm_editor/README.md](tools/pc/fm_editor/README.md)
- Comparar as animação traduzida com o interpretador original:
  `python tools\pc\test_model_recomp.py`
- Decompilação: toda função do jogo bate byte a byte com o original
  (`make tools` e `make match`; vê [notes/setup.md](notes/setup.md)).

<details>
<summary>Progresso da decompilação</summary>

<!-- BEGIN GENERATED PROGRESS -->

| Metric | Current |
|---|---:|
| Game C-decompilation targets matched | **1,134 / 1,134 (100.00%)** |
| Game C-decompilation target bytes matched | **356,080 (`0x56EF0`) / 356,080 (`0x56EF0`) (100.00%)** |
| Remaining game C-decompilation targets | 0 functions, 0 (`0x0`) |
| Evidence-backed handwritten game assembly | 61 functions, 40,116 (`0x9CB4`) |
| Total game-owned functions | 1,195 |
| Preserved Psy-Q CRT/SDK assembly | 591 functions, 117,348 (`0x1CA64`) |
| Total discovered functions | 1,786 |
| Embedded/unassigned resident text | 1,780 (`0x6F4`) |

Runtime overlay modules:

| Module | Matching C functions | Matching C bytes |
|---|---:|---:|
| `free_duel` | 9 / 9 (100.00%) | 4,140 (`0x102C`) / 4,140 (`0x102C`) (100.00%) |
| `main_menu` | 31 / 31 (100.00%) | 17,724 (`0x453C`) / 17,724 (`0x453C`) (100.00%) |
| `overworld_after_coup` | 15 / 15 (100.00%) | 6,184 (`0x1828`) / 6,184 (`0x1828`) (100.00%) |
| `overworld_before_coup` | 15 / 15 (100.00%) | 6,184 (`0x1828`) / 6,184 (`0x1828`) (100.00%) |
| `password` | 27 / 27 (100.00%) | 10,884 (`0x2A84`) / 10,884 (`0x2A84`) (100.00%) |

_Generated from `config/slus_01411/functions.csv` and `config/slus_01411/overlays/*_functions.csv` by `tools/project/progress.py`._

<!-- END GENERATED PROGRESS -->

</details>

---

## Creditos e licenca

- Port pra PC original: [Unchiga e a tropa](https://github.com/Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled),
  licença [MIT](LICENSE) (o aviso de copyright deles fica).
- Decompilação: [memories-decomp](https://github.com/krystalgamer/memories-decomp), dos autores.
- Detalhe em [NOTICE](NOTICE).
- **Yu-Gi-Oh!** e **Forbidden Memories** são da **Konami**. Nenhum arquivo do jogo é
  distribuído aqui.
