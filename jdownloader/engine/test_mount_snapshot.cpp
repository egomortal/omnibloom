#include <cerrno>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <sys/vfs.h>
#define MNT_NOWAIT 2
static int allocations=0,releases=0,mode=0,calls=0;
static void* tracked_alloc(size_t n){if(mode==5)return nullptr;++allocations;return std::malloc(n);}
static void tracked_free(void* p){++releases;std::free(p);}
#define PS5_MOUNT_ALLOC tracked_alloc
#define PS5_MOUNT_FREE tracked_free
#include "ps5MountSnapshot.h"
static int query(struct statfs* entries,long bytes,int flags){++calls;assert(flags==2);if(mode==1){errno=EPERM;return -1;}if(mode==2)return 4097;if(mode==3)return entries?100:500;if(mode==4)return 0;if(mode==6&&entries){errno=EIO;return -1;}if(mode==7&&calls==3){errno=EACCES;return -1;}if(entries){assert(bytes>=1061*(long)sizeof(struct statfs));return 1061;}return 1061;}
static void reset(int kind){mode=kind;calls=allocations=releases=0;errno=0;}
int main(){struct statfs* out=nullptr;int count=-1;reset(0);assert(ps5_mount_snapshot(query,&out,&count)==0&&count==1061&&calls==3&&allocations==1&&releases==0);tracked_free(out);assert(allocations==releases);
 for(int kind=1;kind<=7;++kind){reset(kind);out=nullptr;count=-1;int rc=ps5_mount_snapshot(query,&out,&count);if(kind==4)assert(rc==0&&count==0&&out==nullptr);else assert(rc==-1&&out==nullptr&&count==0);assert(allocations==releases);if(kind==3)assert(calls==24&&errno==EAGAIN);if(kind==6)assert(errno==EIO);if(kind==7)assert(errno==EACCES);}
 std::puts("{\"status\":\"BOUNDED_MOUNT_SNAPSHOT_TESTS_PASS\",\"cases\":8,\"allocations_released_on_failures\":true}");}
