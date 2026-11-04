// Host stand-ins for the PS5 system calls the probe imports. Test only.
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#include <sys/mman.h>
int sceSysmoduleLoadModule(uint16_t id){ return id==207?0:-1; }
int64_t sceKernelGetDirectMemorySize(void){ return 1LL<<34; }
static int64_t next=0x100000;
int sceKernelAllocateDirectMemory(int64_t a,int64_t b,size_t len,size_t al,int t,int64_t*s){(void)a;(void)b;(void)al;(void)t;*s=next;next+=len;return 0;}
int sceKernelMapDirectMemory(void**p,size_t len,int prot,int f,int64_t s,size_t al){(void)prot;(void)f;(void)s;(void)al;
  *p=mmap(0,len,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return *p==MAP_FAILED?-1:0;}
int sceKernelReleaseDirectMemory(int64_t s,size_t l){(void)s;(void)l;return 0;}
int sceKernelMunmap(void*p,size_t l){return munmap(p,l);}
int sceKernelMapNamedFlexibleMemory(void**p,size_t len,int prot,int f,const char*n){(void)prot;(void)f;(void)n;
  *p=mmap(0,len,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);return *p==MAP_FAILED?-1:0;}
int sceKernelAvailableFlexibleMemorySize(size_t*s){*s=448u<<20;return 0;}
uint64_t sceKernelGetProcessTime(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000+t.tv_nsec/1000;}
int sceUserServiceInitialize(const void*p){(void)p;return 0;}
int sceUserServiceGetInitialUser(int*u){*u=0x10000000;return 0;}
typedef struct { char useless[45]; char message[3075]; } notify_request_t;
int sceKernelSendNotificationRequest(int a,notify_request_t*r,size_t s,int b){(void)a;(void)s;(void)b;fprintf(stderr,"[NOTIFY] %s\n",r->message);return 0;}
