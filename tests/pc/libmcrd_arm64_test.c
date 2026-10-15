#define _POSIX_C_SOURCE 200809L
#include "types.h"
#include "pc/guest/state.h"
#include "pc/debug/log.h"
#include "psyq/kernel.h"
#include "psyq/libmcrd.h"
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
_Static_assert(sizeof(struct DIRENTRY)==40,"PS1 entry layout");
static unsigned ticks;
unsigned Platform_VBlankCount(void){return ticks;}
void Platform_WaitVBlank(unsigned ignored){(void)ignored;ticks++;}
int Log_Wanted(LogChannel c){(void)c;return 0;}
int Log_Enabled(LogChannel c){(void)c;return 0;}
void Log_Printf(LogChannel c,const char*f,...){(void)c;(void)f;}
int Memories_StateChunk(MemoriesState*s,const char*t,const MemoriesStateField*f,size_t n){(void)s;(void)t;(void)f;(void)n;abort();}
struct Guard {uint32_t before;PSXLONG value;uint32_t after;};
static void check_guards(struct Guard*g){assert(g->before==0xabcdef01&&g->after==0x12345678);}
int main(void)
{
 char dir[]="/private/tmp/fm-card-XXXXXX",path[256];assert(mkdtemp(dir));
 snprintf(path,sizeof(path),"%s/card.mcd",dir);assert(!setenv("MEMORIES_MEMCARD1",path,1));
 struct Guard command={0xabcdef01,0,0x12345678},result=command,files=command;
 assert(MemCardAccept(0)==1);assert(MemCardSync(0,&command.value,&result.value)==1);
 check_guards(&command);check_guards(&result);assert(command.value==2);
 char name[]="BASLUS-01411-YUGIOH";
 assert(MemCardCreateFile(0,name,1)==0);
 unsigned PSXLONG input[4]={0x5343,0xabcdef01,0x12345678,0xfe};
 unsigned PSXLONG output[4]={0};
 assert(MemCardWriteFile(0,name,input,0,sizeof(input))==1);
 assert(MemCardSync(0,&command.value,&result.value)==1);assert(result.value==0);
 assert(MemCardReadFile(0,name,output,0,sizeof(output))==1);
 assert(MemCardSync(0,&command.value,&result.value)==1);assert(!memcmp(input,output,sizeof(input)));
 struct {uint32_t before;struct DIRENTRY entry;uint32_t after;} directory={.before=0xabcdef01,.after=0x12345678};
 assert(MemCardGetDirentry(0,"*",&directory.entry,&files.value,0,1)==0);
 assert(files.value==1);check_guards(&files);check_guards(&command);check_guards(&result);
 assert(directory.before==0xabcdef01&&directory.after==0x12345678);assert(!strcmp(directory.entry.name,name));assert(directory.entry.size==8192);
 FILE *card=fopen(path,"rb");assert(card);assert(!fseek(card,0,SEEK_END));assert(ftell(card)==0x20000);fclose(card);
 unlink(path);rmdir(dir);puts("PS1 card ABI guards, directory layout, real isolated write/read and raw image size passed");
}
