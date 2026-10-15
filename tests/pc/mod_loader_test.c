#include "pc/mods/object_loader.h"
#include "pc/guest/translated_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
void Duel_InitSideStates(void) {}
void Duel_DrawLifePointsAndDeckCounts(void *object) { (void)object; }
int main(int argc,char **argv) {
    assert(argc==4);
    MemoriesMemory *memory=calloc(1,sizeof(*memory));
    assert(!GuestRuntime_Bind(memory));
    LoadedObject object; char error[512];
    unsigned before=GuestRuntime_RegionCount();
    assert(ObjectLoader_LoadPath(argv[2],&object,error,sizeof(error))==-1);
    assert(!object.native_handle && GuestRuntime_RegionCount()==before);
    assert(ObjectLoader_LoadPath(argv[3],&object,error,sizeof(error))==-1);
    assert(!object.native_handle && GuestRuntime_RegionCount()==before);
    for(int i=0;i<3;i++) {
        int result=ObjectLoader_LoadPath(argv[1],&object,error,sizeof(error));
        if(result) fprintf(stderr,"%s\n",error);
        assert(!result && object.native_handle && object.hash);
        int (*entry)(const void *, void *) = ObjectLoader_Symbol(&object,"MemoriesModInit");
        assert(entry && entry(NULL, NULL) == 7);
        assert(GuestRuntime_RegionCount()>before);
        ObjectLoader_Free(&object);
        assert(!object.native_handle && GuestRuntime_RegionCount()==before);
    }
    GuestRuntime_Reset(); free(memory);
}
