/* LIBGTE register setup over the software coprocessor. */
#include "pc/compat/gte.h"
#include "port_ptr.h" /* G32: the records below live in guest memory */
/* The declarations the game calls through: a definition here that disagrees
 * with one (a host `long` where the library has PSXLONG, say) is a compile
 * error rather than a store of the wrong width on LP64 hosts. */
#include "types.h"
#include "psyq/libgte.h"
#include "psyq/libgpu.h"
#include "psyq/libgs.h"

void InitGeom(void)
{
    Memories_GteReset();
    Memories_GteWriteControl(29, 0x155);      /* ZSF3 */
    Memories_GteWriteControl(30, 0x100);      /* ZSF4 */
    Memories_GteWriteControl(26, 0x3e8);      /* H */
    Memories_GteWriteControl(27, 0xffffef9eu); /* DQA */
    Memories_GteWriteControl(28, 0x1400000);  /* DQB */
    Memories_GteWriteControl(24, 0);
    Memories_GteWriteControl(25, 0);
}

void SetGeomOffset(PSXLONG x, PSXLONG y)
{
    Memories_GteWriteControl(24, (uint32_t)x << 16);
    Memories_GteWriteControl(25, (uint32_t)y << 16);
}

void SetGeomScreen(PSXLONG h)
{
    Memories_GteWriteControl(26, (uint32_t)h);
}

void SetBackColor(PSXLONG r, PSXLONG g, PSXLONG b)
{
    Memories_GteWriteControl(13, (uint32_t)(r << 4));
    Memories_GteWriteControl(14, (uint32_t)(g << 4));
    Memories_GteWriteControl(15, (uint32_t)(b << 4));
}

void SetFarColor(PSXLONG r, PSXLONG g, PSXLONG b)
{
    Memories_GteWriteControl(21, (uint32_t)(r << 4));
    Memories_GteWriteControl(22, (uint32_t)(g << 4));
    Memories_GteWriteControl(23, (uint32_t)(b << 4));
}

void SetFogNearFar(PSXLONG near, PSXLONG far, PSXLONG h)
{
    PSXLONG range = far - near, dqa;
    if (range < 100) {
        return;
    }
    dqa = (((-near * far) / range) << 8) / h;
    dqa = dqa < -32767 ? -32767 : dqa > 32767 ? 32767 : dqa;
    Memories_GteWriteControl(27, (uint32_t)dqa);
    Memories_GteWriteControl(28, (uint32_t)(((far << 12) / range) << 12));
}

/* MATRIX: short m[3][3], two bytes of padding, long t[3]. */
static void load_matrix(unsigned base, const short *m)
{
    Memories_GteWriteControl(base, (uint16_t)m[0] | ((uint32_t)(uint16_t)m[1] << 16));
    Memories_GteWriteControl(base + 1, (uint16_t)m[2] | ((uint32_t)(uint16_t)m[3] << 16));
    Memories_GteWriteControl(base + 2, (uint16_t)m[4] | ((uint32_t)(uint16_t)m[5] << 16));
    Memories_GteWriteControl(base + 3, (uint16_t)m[6] | ((uint32_t)(uint16_t)m[7] << 16));
    Memories_GteWriteControl(base + 4, (uint16_t)m[8]);
}

void SetRotMatrix(MATRIX *matrix) { load_matrix(0, matrix->m[0]); }
void SetLightMatrix(MATRIX *matrix) { load_matrix(8, matrix->m[0]); }
void SetColorMatrix(MATRIX *matrix) { load_matrix(16, matrix->m[0]); }

void SetTransMatrix(MATRIX *matrix)
{
    const int32_t *t = (const int32_t *)((const char *)matrix + 20);
    Memories_GteWriteControl(5, (uint32_t)t[0]);
    Memories_GteWriteControl(6, (uint32_t)t[1]);
    Memories_GteWriteControl(7, (uint32_t)t[2]);
}

static uint32_t matrix_stack[20][8];
static int matrix_depth;

void PushMatrix(void)
{
    unsigned i;
    if (matrix_depth < 20) {
        for (i = 0; i < 8; i++) {
            matrix_stack[matrix_depth][i] = Memories_GteReadControl(i);
        }
        matrix_depth++;
    }
}

void PopMatrix(void)
{
    unsigned i;
    if (matrix_depth > 0) {
        matrix_depth--;
        for (i = 0; i < 8; i++) {
            Memories_GteWriteControl(i, matrix_stack[matrix_depth][i]);
        }
    }
}

#include "pc/guest/state.h"

/* The library's own tables, read from the resident image so every value is
 * the retail one: a quarter wave of sin (0..0x400) for rsin/rcos, and 4096
 * {sin, cos} pairs for the matrix builders. */
#define SIN_QUARTER ((const int16_t *)0x80094938u)
#define SIN_COS ((const int16_t *)0x80095638u)

static int sin_1(int angle)
{
    if (angle <= 0x400) { return SIN_QUARTER[angle]; }
    if (angle <= 0x800) { return SIN_QUARTER[0x800 - angle]; }
    if (angle <= 0xc00) { return -SIN_QUARTER[angle - 0x800]; }
    return -SIN_QUARTER[0x1000 - angle];
}

int rsin(int angle) { return angle < 0 ? -sin_1(-angle & 0xfff) : sin_1(angle & 0xfff); }
int rcos(int angle) { return sin_1(((angle < 0 ? -angle : angle) + 0x400) & 0xfff); }

/* The game also links Psy-Q's CORDIC-flavoured entry points. They use the
 * same 12-bit angle and 1.3.12 result contract as rsin/rcos; game references
 * are renamed so they cannot bind to libc's complex-number functions. */
int Psx_csin(int angle) { return rsin(angle); }
int Psx_ccos(int angle) { return rcos(angle); }

/* The library's records under the names this file has always used. */
typedef MATRIX Matrix;
typedef SVECTOR ShortVector;
typedef VECTOR LongVector;

/* The console's layouts, which the game's data and the GTE code above share. */
_Static_assert(sizeof(MATRIX) == 32 && sizeof(VECTOR) == 16 && sizeof(SVECTOR) == 8 && sizeof(CVECTOR) == 4 &&
                   sizeof(DVECTOR) == 4,
               "Psy-Q GTE records must keep their 32-bit layouts");

static void sin_cos(int angle, int *sine, int *cosine)
{
    const int16_t *pair = &SIN_COS[((angle < 0 ? -angle : angle) & 0xfff) * 2];
    *sine = angle < 0 ? -pair[0] : pair[0];
    *cosine = pair[1];
}

/* Ported from the resident routine, including where it negates before the
 * shift (which rounds the other way). Rotation order X, Y, Z. */
Matrix *RotMatrix(ShortVector *r, Matrix *m)
{
    int sx, cx, sy, cy, sz, cz, t;
    sin_cos(r->vx, &sx, &cx);
    sin_cos(r->vy, &sy, &cy);
    sin_cos(r->vz, &sz, &cz);
    m->m[0][2] = (short)sy;
    m->m[1][2] = (short)(-(cy * sx) >> 12);
    m->m[2][2] = (short)((cy * cx) >> 12);
    m->m[0][0] = (short)((cz * cy) >> 12);
    m->m[0][1] = (short)(-(sz * cy) >> 12);
    t = (cz * -sy) >> 12;
    m->m[1][0] = (short)(((sz * cx) >> 12) - ((t * sx) >> 12));
    m->m[2][0] = (short)(((sz * sx) >> 12) + ((t * cx) >> 12));
    t = (sz * -sy) >> 12;
    m->m[1][1] = (short)(((cz * cx) >> 12) + ((t * sx) >> 12));
    m->m[2][1] = (short)(((cz * sx) >> 12) - ((t * cx) >> 12));
    return m;
}

/* Rotation order Z, Y, X. The resident routine multiplies on the GTE (GPF);
 * with 1.3.12 inputs that is a plain product shifted right by 12. */
Matrix *RotMatrixZYX_gte(ShortVector *r, Matrix *m)
{
    int sx, cx, sy, cy, sz, cz, sxsy, cxsy;
    sin_cos(r->vx, &sx, &cx);
    sin_cos(r->vy, &sy, &cy);
    sin_cos(r->vz, &sz, &cz);
    sxsy = (sx * sy) >> 12;
    cxsy = (cx * sy) >> 12;
    m->m[0][0] = (short)((cz * cy) >> 12);
    m->m[0][1] = (short)(((cz * sxsy) >> 12) - ((cx * sz) >> 12));
    m->m[0][2] = (short)(((cz * cxsy) >> 12) + ((sx * sz) >> 12));
    m->m[1][0] = (short)((sz * cy) >> 12);
    m->m[1][1] = (short)(((sz * sxsy) >> 12) + ((cx * cz) >> 12));
    m->m[1][2] = (short)(((sz * cxsy) >> 12) - ((sx * cz) >> 12));
    m->m[2][0] = (short)-sy;
    m->m[2][1] = (short)((cy * sx) >> 12);
    m->m[2][2] = (short)((cy * cx) >> 12);
    return m;
}

/* As RotMatrix, but the resident routine multiplies on the GTE and negates
 * after the shift rather than before it. */
Matrix *RotMatrix_gte(ShortVector *r, Matrix *m)
{
    int sx, cx, sy, cy, sz, cz, sxsy, cxsy;
    sin_cos(r->vx, &sx, &cx);
    sin_cos(r->vy, &sy, &cy);
    sin_cos(r->vz, &sz, &cz);
    sxsy = (sx * sy) >> 12;
    cxsy = (cx * sy) >> 12;
    m->m[0][0] = (short)((cz * cy) >> 12);
    m->m[0][1] = (short)-((sz * cy) >> 12);
    m->m[0][2] = (short)sy;
    m->m[1][0] = (short)(((cz * sxsy) >> 12) + ((cx * sz) >> 12));
    m->m[1][1] = (short)(((cx * cz) >> 12) - ((sz * sxsy) >> 12));
    m->m[1][2] = (short)-((cy * sx) >> 12);
    m->m[2][0] = (short)(((sx * sz) >> 12) - ((cz * cxsy) >> 12));
    m->m[2][1] = (short)(((sx * cz) >> 12) + ((sz * cxsy) >> 12));
    m->m[2][2] = (short)((cy * cx) >> 12);
    return m;
}

/* Rotation order Z, X, Y, from the resident routine (0x800889C0), which
 * multiplies on the CPU and negates before the shift. The Exodia win's model
 * scene calls it. */
Matrix *RotMatrixZXY(ShortVector *r, Matrix *m)
{
    int sx, cx, sy, cy, sz, cz, sxsy, sxcy;
    sin_cos(r->vx, &sx, &cx);
    sin_cos(r->vy, &sy, &cy);
    sin_cos(r->vz, &sz, &cz);
    m->m[2][1] = (short)sx;
    m->m[2][0] = (short)(-(cx * sy) >> 12);
    m->m[2][2] = (short)((cx * cy) >> 12);
    m->m[1][1] = (short)((cz * cx) >> 12);
    m->m[0][1] = (short)(-(sz * cx) >> 12);
    sxsy = (sx * sy) >> 12;
    m->m[0][0] = (short)(((cz * cy) >> 12) - ((sxsy * sz) >> 12));
    m->m[1][0] = (short)(((sz * cy) >> 12) + ((sxsy * cz) >> 12));
    sxcy = (sx * cy) >> 12;
    m->m[0][2] = (short)(((cz * sy) >> 12) + ((sxcy * sz) >> 12));
    m->m[1][2] = (short)(((sz * sy) >> 12) - ((sxcy * cz) >> 12));
    return m;
}

/* Rotation order Y, X, Z, from the resident GTE routine. */
Matrix *RotMatrixYXZ_gte(ShortVector *r, Matrix *m)
{
    int sx, cx, sy, cy, sz, cz, sysx, cysx;
    sin_cos(r->vx, &sx, &cx);
    sin_cos(r->vy, &sy, &cy);
    sin_cos(r->vz, &sz, &cz);
    sysx = (sy * sx) >> 12;
    cysx = (cy * sx) >> 12;
    m->m[0][0] = (short)(((cy * cz) >> 12) + ((sz * sysx) >> 12));
    m->m[0][1] = (short)(((cz * sysx) >> 12) - ((cy * sz) >> 12));
    m->m[0][2] = (short)((cx * sy) >> 12);
    m->m[1][0] = (short)((sz * cx) >> 12);
    m->m[1][1] = (short)((cz * cx) >> 12);
    m->m[1][2] = (short)-sx;
    m->m[2][0] = (short)(((sz * cysx) >> 12) - ((sy * cz) >> 12));
    m->m[2][1] = (short)(((cz * cysx) >> 12) + ((sy * sz) >> 12));
    m->m[2][2] = (short)((cx * cy) >> 12);
    return m;
}

/* Angle of (x, y) in 4096ths of a turn, from the library's arctangent table
 * (0x80099638: atan of n/1024 for n = 0..1024). The smaller magnitude is
 * divided by the larger, pre-shifting whichever keeps the quotient in range. */
PSXLONG ratan2(PSXLONG y, PSXLONG x)
{
    const int16_t *table = (const int16_t *)0x80099638u;
    int negative_x = x < 0, negative_y = y < 0;
    int32_t ax = negative_x ? -(int32_t)x : (int32_t)x, ay = negative_y ? -(int32_t)y : (int32_t)y, angle;
    if (!ax && !ay) {
        return 0;
    }
    if (ay < ax) {
        angle = table[ay & 0x7fe00000 ? ay / (ax >> 10) : (int32_t)((uint32_t)ay << 10) / ax];
    } else {
        angle = 0x400 - table[ax & 0x7fe00000 ? ax / (ay >> 10) : (int32_t)((uint32_t)ax << 10) / ay];
    }
    if (negative_x) {
        angle = 0x800 - angle;
    }
    return negative_y ? -angle : angle;
}

/* The matrix products run on the GTE in the library, one MVMVA per column,
 * and leave the rotation matrix and IR/MAC registers as the hardware would;
 * they are issued the same way here so the saturation rules are the GTE's. */
#define MVMVA_ROTATE_V0 0x0486012u /* sf=1, rotation matrix, V0, no translation */
#define MVMVA_ROTATE_IR 0x049e012u /* sf=1, rotation matrix, IR vector */
#define MVMVA_ROTATE_IR_UNSHIFTED 0x041e012u

static void multiply(const Matrix *a, const Matrix *b, Matrix *out)
{
    short result[3][3];
    int column, row;
    load_matrix(0, a->m[0]);
    for (column = 0; column < 3; column++) {
        Memories_GteWriteData(0, (uint16_t)b->m[0][column] | ((uint32_t)(uint16_t)b->m[1][column] << 16));
        Memories_GteWriteData(1, (uint32_t)(int32_t)b->m[2][column]);
        Memories_GteCommand(MVMVA_ROTATE_V0);
        for (row = 0; row < 3; row++) {
            result[row][column] = (short)Memories_GteReadData(9 + (unsigned)row);
        }
    }
    for (row = 0; row < 3; row++) {
        for (column = 0; column < 3; column++) {
            out->m[row][column] = result[row][column];
        }
    }
    /* the routine stores IR3 as a whole word, into the padding after m[2][2] */
    *(short *)((char *)out + 18) = (short)(result[2][2] < 0 ? -1 : 0);
}

Matrix *MulMatrix(Matrix *m0, Matrix *m1) { multiply(m0, m1, m0); return m0; }
Matrix *MulMatrix2(Matrix *m0, Matrix *m1) { multiply(m0, m1, m1); return m1; }

/* Matrix times a 32-bit vector: each component goes through as a 15-bit low
 * part (shifted product) and a signed high part (unshifted product << 3). */
LongVector *ApplyMatrixLV(Matrix *m, LongVector *v, LongVector *out)
{
    int32_t in[3] = {v->vx, v->vy, v->vz}, high[3], low[3], upper[3];
    int i;
    load_matrix(0, m->m[0]);
    for (i = 0; i < 3; i++) {
        if (in[i] < 0) {
            uint32_t magnitude = (uint32_t)-in[i];
            high[i] = -(int32_t)(magnitude >> 15);
            low[i] = -(int32_t)(magnitude & 0x7fff);
        } else {
            high[i] = in[i] >> 15;
            low[i] = in[i] & 0x7fff;
        }
    }
    for (i = 0; i < 3; i++) {
        Memories_GteWriteData(9 + (unsigned)i, (uint32_t)high[i]);
    }
    Memories_GteCommand(MVMVA_ROTATE_IR_UNSHIFTED);
    for (i = 0; i < 3; i++) {
        upper[i] = (int32_t)Memories_GteReadData(25 + (unsigned)i);
        Memories_GteWriteData(9 + (unsigned)i, (uint32_t)low[i]);
    }
    Memories_GteCommand(MVMVA_ROTATE_IR);
    out->vx = (int32_t)(Memories_GteReadData(25) + ((uint32_t)upper[0] << 3));
    out->vy = (int32_t)(Memories_GteReadData(26) + ((uint32_t)upper[1] << 3));
    out->vz = (int32_t)(Memories_GteReadData(27) + ((uint32_t)upper[2] << 3));
    return out;
}

Matrix *TransposeMatrix(Matrix *m0, Matrix *m1)
{
    short copy[3][3];
    int row, column;
    for (row = 0; row < 3; row++) {
        for (column = 0; column < 3; column++) {
            copy[row][column] = m0->m[column][row];
        }
    }
    for (row = 0; row < 3; row++) {
        for (column = 0; column < 3; column++) {
            m1->m[row][column] = copy[row][column];
        }
    }
    return m1;
}

/* Integer square root through the library's table (192 entries from
 * 0x800951A8), normalized with the GTE's leading-zero counter. */
PSXLONG SquareRoot0(PSXLONG value)
{
    const int16_t *table = (const int16_t *)0x800951a8u;
    int zeros, even, shift;
    int32_t index;
    Memories_GteWriteData(30, (uint32_t)value);
    zeros = (int)Memories_GteReadData(31);
    if (zeros == 32) {
        return 0;
    }
    even = zeros & ~1;
    shift = (31 - even) >> 1;
    index = even - 24 < 0 ? (int32_t)value >> (24 - even) : (int32_t)((uint32_t)value << (even - 24));
    return (PSXLONG)(((uint32_t)(int32_t)table[index - 0x40] << shift) >> 12);
}

Matrix *ScaleMatrix(Matrix *m, LongVector *v)
{
    int i;
    for (i = 0; i < 3; i++) {
        m->m[i][0] = (short)((m->m[i][0] * v->vx) >> 12);
        m->m[i][1] = (short)((m->m[i][1] * v->vy) >> 12);
        m->m[i][2] = (short)((m->m[i][2] * v->vz) >> 12);
    }
    return m;
}

PSXLONG ReadGeomScreen(void) { return (PSXLONG)(Memories_GteReadControl(26) & 0xffff); }

PSXLONG RotTransPers(ShortVector *v, PSXLONG *sxy, PSXLONG *p, PSXLONG *flag)
{
    Memories_GteLoad(0, v);
    Memories_GteLoad(1, &v->vz);
    Memories_GteCommand(0x0180001);
    *sxy = (PSXLONG)Memories_GteReadData(14);
    *p = (PSXLONG)Memories_GteReadData(8);
    *flag = (PSXLONG)Memories_GteReadControl(31);
    return (PSXLONG)Memories_GteReadData(19) >> 2;
}

/* Project three or four vertices, stop at a back face, otherwise report the
 * screen points, the last interpolation value and the average depth. */
PSXLONG RotAverageNclip3(ShortVector *v0, ShortVector *v1, ShortVector *v2, PSXLONG *sxy0, PSXLONG *sxy1, PSXLONG *sxy2,
                      PSXLONG *p, PSXLONG *otz, PSXLONG *flag)
{
    PSXLONG opz;
    Memories_GteLoad(0, v0);
    Memories_GteLoad(1, &v0->vz);
    Memories_GteLoad(2, v1);
    Memories_GteLoad(3, &v1->vz);
    Memories_GteLoad(4, v2);
    Memories_GteLoad(5, &v2->vz);
    Memories_GteCommand(0x0280030);
    *flag = (PSXLONG)Memories_GteReadControl(31);
    Memories_GteCommand(0x1400006);
    opz = (PSXLONG)Memories_GteReadData(24);
    if (opz <= 0) {
        return opz;
    }
    Memories_GteStore(12, sxy0);
    Memories_GteStore(13, sxy1);
    Memories_GteStore(14, sxy2);
    Memories_GteStore(8, p);
    Memories_GteCommand(0x158002d);
    *otz = (PSXLONG)Memories_GteReadData(7);
    return opz;
}

/* The "no memory" form: results stay in the GTE for the caller's inline
 * reads; only the flag word comes back. */
PSXLONG RotAverageNclip3_nom(ShortVector *v0, ShortVector *v1, ShortVector *v2)
{
    PSXLONG flag;
    Memories_GteLoad(0, v0);
    Memories_GteLoad(1, &v0->vz);
    Memories_GteLoad(2, v1);
    Memories_GteLoad(3, &v1->vz);
    Memories_GteLoad(4, v2);
    Memories_GteLoad(5, &v2->vz);
    Memories_GteCommand(0x0280030);
    flag = (PSXLONG)Memories_GteReadControl(31);
    Memories_GteCommand(0x158002d);
    Memories_GteCommand(0x1400006);
    return flag;
}

PSXLONG RotAverageNclip4(ShortVector *v0, ShortVector *v1, ShortVector *v2, ShortVector *v3, PSXLONG *sxy0, PSXLONG *sxy1,
                      PSXLONG *sxy2, PSXLONG *sxy3, PSXLONG *p, PSXLONG *otz, PSXLONG *flag)
{
    PSXLONG opz;
    Memories_GteLoad(0, v0);
    Memories_GteLoad(1, &v0->vz);
    Memories_GteLoad(2, v1);
    Memories_GteLoad(3, &v1->vz);
    Memories_GteLoad(4, v2);
    Memories_GteLoad(5, &v2->vz);
    Memories_GteCommand(0x0280030);
    *flag = (PSXLONG)Memories_GteReadControl(31);
    Memories_GteCommand(0x1400006);
    opz = (PSXLONG)Memories_GteReadData(24);
    if (opz <= 0) {
        return opz;
    }
    Memories_GteStore(12, sxy0);
    Memories_GteStore(13, sxy1);
    Memories_GteStore(14, sxy2);
    Memories_GteLoad(0, v3);
    Memories_GteLoad(1, &v3->vz);
    Memories_GteCommand(0x0180001);
    Memories_GteStore(14, sxy3);
    *flag |= (PSXLONG)Memories_GteReadControl(31);
    Memories_GteStore(8, p);
    Memories_GteCommand(0x168002e);
    *otz = (PSXLONG)Memories_GteReadData(7);
    return opz;
}

/* The remaining projection and lighting wrappers, each the resident
 * routine's sequence of loads, one or two GTE commands and stores. */
static void load_vertex(unsigned index, const ShortVector *v)
{
    Memories_GteLoad(index * 2, v);
    Memories_GteLoad(index * 2 + 1, &v->vz);
}

PSXLONG RotAverage3(ShortVector *v0, ShortVector *v1, ShortVector *v2, PSXLONG *sxy0, PSXLONG *sxy1, PSXLONG *sxy2, PSXLONG *p,
                 PSXLONG *flag)
{
    load_vertex(0, v0);
    load_vertex(1, v1);
    load_vertex(2, v2);
    Memories_GteCommand(0x0280030);
    Memories_GteStore(12, sxy0);
    Memories_GteStore(13, sxy1);
    Memories_GteStore(14, sxy2);
    Memories_GteStore(8, p);
    *flag = (PSXLONG)Memories_GteReadControl(31);
    Memories_GteCommand(0x158002d);
    return (PSXLONG)Memories_GteReadData(7);
}

PSXLONG RotAverage4(ShortVector *v0, ShortVector *v1, ShortVector *v2, ShortVector *v3, PSXLONG *sxy0, PSXLONG *sxy1,
                 PSXLONG *sxy2, PSXLONG *sxy3, PSXLONG *p, PSXLONG *flag)
{
    uint32_t first;
    load_vertex(0, v0);
    load_vertex(1, v1);
    load_vertex(2, v2);
    Memories_GteCommand(0x0280030);
    Memories_GteStore(12, sxy0);
    Memories_GteStore(13, sxy1);
    Memories_GteStore(14, sxy2);
    first = Memories_GteReadControl(31);
    load_vertex(0, v3);
    Memories_GteCommand(0x0180001);
    Memories_GteStore(14, sxy3);
    Memories_GteStore(8, p);
    *flag = (PSXLONG)(Memories_GteReadControl(31) | first);
    Memories_GteCommand(0x168002e);
    return (PSXLONG)Memories_GteReadData(7);
}

PSXLONG AverageZ3(PSXLONG sz0, PSXLONG sz1, PSXLONG sz2)
{
    Memories_GteWriteData(17, (uint32_t)sz0);
    Memories_GteWriteData(18, (uint32_t)sz1);
    Memories_GteWriteData(19, (uint32_t)sz2);
    Memories_GteCommand(0x158002d);
    return (PSXLONG)Memories_GteReadData(7);
}

PSXLONG NormalClip(PSXLONG sxy0, PSXLONG sxy1, PSXLONG sxy2)
{
    Memories_GteWriteData(12, (uint32_t)sxy0);
    Memories_GteWriteData(14, (uint32_t)sxy2);
    Memories_GteWriteData(13, (uint32_t)sxy1);
    Memories_GteCommand(0x1400006);
    return (PSXLONG)Memories_GteReadData(24);
}

#define MVMVA_ROTATE_TRANSLATE_V0 0x0480012u /* sf=1, rotation matrix, V0, translation vector */

void RotTrans(ShortVector *v0, LongVector *v1, PSXLONG *flag)
{
    load_vertex(0, v0);
    Memories_GteCommand(MVMVA_ROTATE_TRANSLATE_V0);
    v1->vx = (int32_t)Memories_GteReadData(25);
    v1->vy = (int32_t)Memories_GteReadData(26);
    v1->vz = (int32_t)Memories_GteReadData(27);
    *flag = (PSXLONG)Memories_GteReadControl(31);
}

void RotTransSV(ShortVector *v0, ShortVector *v1, PSXLONG *flag)
{
    uint32_t z;
    load_vertex(0, v0);
    Memories_GteCommand(MVMVA_ROTATE_TRANSLATE_V0);
    v1->vx = (short)Memories_GteReadData(9);
    v1->vy = (short)Memories_GteReadData(10);
    z = Memories_GteReadData(11); /* stored as a word: z and the pad after it */
    v1->vz = (short)z;
    v1->pad = (short)(z >> 16);
    *flag = (PSXLONG)Memories_GteReadControl(31);
}

void RotTransPersN(ShortVector *v0, DVECTOR *v1, uint16_t *sz, uint16_t *p, uint16_t *flag, PSXLONG n)
{
    do {
        load_vertex(0, v0++);
        Memories_GteCommand(0x0180001);
        *(int32_t *)v1++ = (int32_t)Memories_GteReadData(14); /* SXY2 as one word */
        *sz++ = (uint16_t)Memories_GteReadData(19);
        *p++ = (uint16_t)Memories_GteReadData(8);
        *flag++ = (uint16_t)(Memories_GteReadControl(31) >> 12);
    } while (--n > 0);
}

PSXLONG RotColorDpq(ShortVector *v0, ShortVector *v1, CVECTOR *v2, PSXLONG *sxy, CVECTOR *v3, PSXLONG *flag)
{
    load_vertex(0, v0);
    Memories_GteCommand(0x0180001);
    *flag = (PSXLONG)Memories_GteReadControl(31);
    Memories_GteStore(14, sxy);
    load_vertex(0, v1);
    Memories_GteLoad(6, v2);
    Memories_GteCommand(0x0e80413);
    Memories_GteStore(22, v3);
    return (PSXLONG)(int32_t)Memories_GteReadData(19) >> 2;
}

void NormalColorCol(ShortVector *v0, CVECTOR *v1, CVECTOR *v2)
{
    load_vertex(0, v0);
    Memories_GteLoad(6, v1);
    Memories_GteCommand(0x108041b);
    Memories_GteStore(22, v2);
}

/* Polygon subdivision (DivideFT4), from the resident routines. A textured
 * quad is projected; if it faces the viewer it is split `ndiv` times into
 * four, each level re-projecting the edge midpoints and the centre so the
 * texture follows the perspective, and the leaves are linked into the
 * ordering table as POLY_FT4 packets. Quads wholly nearer than H/2 or wholly
 * outside the clip window around the screen offset are dropped at any level.
 * The work area is the caller's DIVPOLYGON4, laid out as in libgte.h. */
typedef struct DivideVertex {
    ShortVector v;
    uint8_t uv[2];
    uint16_t pad;
    uint32_t color;
    int16_t sx, sy;
    uint32_t sz;
} DivideVertex;

typedef struct DivideLevel {
    DivideVertex r01, r02, r31, r32, centre;
    DivideVertex *G32 corner[4];
    uint32_t *G32 unused_return;
} DivideLevel;

typedef struct DividePolygon4 {
    uint32_t ndiv, pih, piv;
    uint16_t clut, tpage;
    uint32_t rgbc;
    uint32_t *G32 ot;
    DivideVertex r[4];
    DivideLevel level[5];
} DividePolygon4;

_Static_assert(sizeof(DivideVertex) == 0x18 && sizeof(DivideLevel) == 0x8c, "DIVPOLYGON4 layout");
_Static_assert(sizeof(DivideVertex) == sizeof(RVECTOR) && sizeof(DivideLevel) == sizeof(CRVECTOR4) &&
                   sizeof(DividePolygon4) == sizeof(DIVPOLYGON4),
               "DividePolygon4 is libgte.h's DIVPOLYGON4");

static uint32_t *emit_ft4(uint32_t *packet, DividePolygon4 *work, const DivideVertex *a, const DivideVertex *b,
                          const DivideVertex *c, const DivideVertex *d)
{
    const DivideVertex *corner[4] = {a, b, c, d};
    int i;
    for (i = 0; i < 4; i++) {
        uint32_t uv = (uint16_t)(corner[i]->uv[0] | (corner[i]->uv[1] << 8));
        packet[2 + i * 2] = (uint16_t)corner[i]->sx | ((uint32_t)(uint16_t)corner[i]->sy << 16);
        packet[3 + i * 2] = i == 0 ? uv | ((uint32_t)work->clut << 16) : i == 1 ? uv | ((uint32_t)work->tpage << 16) : uv;
    }
    packet[1] = work->rgbc;
    packet[0] = *work->ot | 0x09000000u;
    *work->ot = (uint32_t)(uintptr_t)packet & 0x00ffffffu;
    return packet + 10;
}

static void store_screen(DivideVertex *vertex, unsigned sxy, unsigned sz)
{
    uint32_t word = Memories_GteReadData(sxy);
    vertex->sx = (int16_t)word;
    vertex->sy = (int16_t)(word >> 16);
    if (sz) {
        vertex->sz = Memories_GteReadData(sz);
    }
}

static uint32_t *divide_ft4(uint32_t *packet, DividePolygon4 *work, uint32_t depth, DivideLevel *level)
{
    DivideVertex *G32 *r = level->corner;
    int32_t near_limit = (int32_t)Memories_GteReadControl(26) >> 1;
    int32_t centre_x = (int32_t)Memories_GteReadControl(24) >> 16, centre_y = (int32_t)Memories_GteReadControl(25) >> 16;
    int32_t half_w = (int32_t)(work->pih >> 1), half_h = (int32_t)(work->piv >> 1);
    int i;
#define ALL(test) (test(0) && test(1) && test(2) && test(3))
#define TOO_NEAR(i) (r[i]->sz < (uint32_t)near_limit)
#define RIGHT_OF(i) (centre_x + half_w < r[i]->sx)
#define LEFT_OF(i) (r[i]->sx < centre_x - half_w)
#define BELOW(i) (centre_y + half_h < r[i]->sy)
#define ABOVE(i) (r[i]->sy < centre_y - half_h)
    if (ALL(TOO_NEAR) || ALL(RIGHT_OF) || ALL(LEFT_OF) || ALL(BELOW) || ALL(ABOVE)) {
        return packet;
    }
#undef ALL
#undef TOO_NEAR
#undef RIGHT_OF
#undef LEFT_OF
#undef BELOW
#undef ABOVE
    for (i = 0; i < 3; i++) {
        const short c0 = (&r[0]->v.vx)[i], c1 = (&r[1]->v.vx)[i], c2 = (&r[2]->v.vx)[i], c3 = (&r[3]->v.vx)[i];
        (&level->r31.v.vx)[i] = (short)((c3 + c1) >> 1);
        (&level->r02.v.vx)[i] = (short)((c0 + c2) >> 1);
        (&level->r01.v.vx)[i] = (short)((c0 + c1) >> 1);
        (&level->r32.v.vx)[i] = (short)((c3 + c2) >> 1);
        (&level->centre.v.vx)[i] = (short)((c0 + c1 + c3 + c2) >> 2);
    }
    for (i = 0; i < 2; i++) {
        const int t0 = r[0]->uv[i], t1 = r[1]->uv[i], t2 = r[2]->uv[i], t3 = r[3]->uv[i];
        level->r31.uv[i] = (uint8_t)((t3 + t1) >> 1);
        level->r02.uv[i] = (uint8_t)((t0 + t2) >> 1);
        level->r01.uv[i] = (uint8_t)((t0 + t1) >> 1);
        level->r32.uv[i] = (uint8_t)((t3 + t2) >> 1);
        level->centre.uv[i] = (uint8_t)((t0 + t1 + t3 + t2) >> 2);
    }
    Memories_GteLoad(0, &level->r01.v);
    Memories_GteLoad(1, &level->r01.v.vz);
    Memories_GteLoad(2, &level->r02.v);
    Memories_GteLoad(3, &level->r02.v.vz);
    Memories_GteLoad(4, &level->centre.v);
    Memories_GteLoad(5, &level->centre.v.vz);
    Memories_GteCommand(0x0280030);
    store_screen(&level->r01, 12, 17);
    store_screen(&level->r02, 13, 18);
    store_screen(&level->centre, 14, 19);
    Memories_GteLoad(0, &level->r31.v);
    Memories_GteLoad(1, &level->r31.v.vz);
    Memories_GteLoad(2, &level->r32.v);
    Memories_GteLoad(3, &level->r32.v.vz);
    Memories_GteCommand(0x0280030); /* the centre rides along as V2 again */
    depth++;
    if (work->ndiv == depth) {
        store_screen(&level->r31, 12, 0);
        store_screen(&level->r32, 13, 0);
        packet = emit_ft4(packet, work, r[0], &level->r01, &level->r02, &level->centre);
        packet = emit_ft4(packet, work, r[1], &level->r31, &level->r01, &level->centre);
        packet = emit_ft4(packet, work, r[2], &level->r02, &level->r32, &level->centre);
        packet = emit_ft4(packet, work, r[3], &level->r32, &level->r31, &level->centre);
    } else {
        DivideLevel *next = level + 1;
        DivideVertex *quarters[4][3] = {{&level->r01, &level->r02, NULL}, {&level->r31, &level->r01, NULL},
                                        {&level->r02, &level->r32, NULL}, {&level->r32, &level->r31, NULL}};
        store_screen(&level->r31, 12, 17);
        store_screen(&level->r32, 13, 18);
        for (i = 0; i < 4; i++) {
            next->corner[0] = r[i];
            next->corner[1] = quarters[i][0];
            next->corner[2] = quarters[i][1];
            next->corner[3] = &level->centre;
            packet = divide_ft4(packet, work, depth, next);
        }
    }
    return packet;
}

POLY_FT4 *DivideFT4(SVECTOR *v0, SVECTOR *v1, SVECTOR *v2, SVECTOR *v3, u32 *uv0, u32 *uv1, u32 *uv2, u32 *uv3,
                    CVECTOR *color, POLY_FT4 *first, u32 *ot, DIVPOLYGON4 *divp)
{
    uint32_t *packet = (uint32_t *)first, *rgbc = (uint32_t *)color;
    DividePolygon4 *work = (DividePolygon4 *)divp;
    const ShortVector *corners[4] = {v0, v1, v2, v3};
    const uint32_t *texture[4] = {uv0, uv1, uv2, uv3};
    PSXLONG sxy[4], p, otz, flag;
    int i;
    for (i = 0; i < 4; i++) {
        work->level[0].corner[i] = &work->r[i];
        work->r[i].v = *corners[i];
    }
    if (RotAverageNclip4(&work->r[0].v, &work->r[1].v, &work->r[2].v, &work->r[3].v, &sxy[0], &sxy[1], &sxy[2],
                         &sxy[3], &p, &otz, &flag) <= 0) {
        return first;
    }
    for (i = 0; i < 4; i++) {
        work->r[i].sx = (int16_t)sxy[i];
        work->r[i].sy = (int16_t)((uint32_t)sxy[i] >> 16);
        work->r[i].sz = Memories_GteReadData(16 + (unsigned)i);
        work->r[i].uv[0] = (uint8_t)*texture[i];
        work->r[i].uv[1] = (uint8_t)(*texture[i] >> 8);
        work->r[i].pad = (uint16_t)(*texture[i] >> 16);
    }
    work->ot = ot;
    work->rgbc = *rgbc;
    work->clut = (uint16_t)(*uv0 >> 16);
    work->tpage = (uint16_t)(*uv1 >> 16);
    return (POLY_FT4 *)divide_ft4(packet, work, 0, &work->level[0]);
}

void LibGte_State(MemoriesState *state)
{
    const MemoriesStateField fields[] = {{matrix_stack, sizeof(matrix_stack)}, {&matrix_depth, sizeof(matrix_depth)}};
    Memories_StateChunk(state, "libgte", fields, 2);
}
