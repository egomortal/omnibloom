#include "own_uid.hpp"
#include <cassert>
#include <cstdio>
#include <initializer_list>
static uid_t ruid,euid;static gid_t rgid,egid;static int calls,group_reads,behavior;static uid_t argument;
static uid_t get_r(){return ruid;}static uid_t get_e(){return euid;}static gid_t get_g(){return rgid;}static gid_t get_eg(){return egid;}
static int get_groups(int capacity,gid_t* groups){assert(capacity==32);++group_reads;if(behavior==1||behavior==8)return behavior==1?-1:33;if(behavior==5&&group_reads==2)return -1;groups[0]=(behavior==3&&group_reads==2)?2:1;return 1;}
static int set_uid(uid_t value){++calls;argument=value;if(behavior==2)return -1;if(behavior!=4)ruid=value;if(behavior==6)rgid=2;if(behavior==7)euid=1;return 0;}
static OwnUidApi api{get_r,get_e,get_g,get_eg,get_groups,set_uid};
static void reset(uid_t real,uid_t effective,int kind=0){ruid=real;euid=effective;rgid=egid=1;calls=group_reads=0;behavior=kind;argument=999;}
int main(){
 reset(1,0);auto out=normalize_own_uid(api);assert(out.reason==0&&out.attempted&&out.groups_unchanged&&calls==1&&argument==0&&out.after.real_uid==0);
 reset(0,0);out=normalize_own_uid(api);assert(out.reason==0&&!out.attempted&&calls==0&&group_reads==2);
 for(auto pair:{OwnUidSnapshot{2,0},OwnUidSnapshot{1,1},OwnUidSnapshot{0,1}}){reset(pair.real_uid,pair.effective_uid);out=normalize_own_uid(api);assert(out.reason==2&&!out.attempted&&calls==0);}
 reset(1,0,1);out=normalize_own_uid(api);assert(out.reason==1&&calls==0);
 reset(1,0,8);out=normalize_own_uid(api);assert(out.reason==1&&calls==0);
 reset(1,0,2);out=normalize_own_uid(api);assert(out.reason==3&&out.attempted&&calls==1);
 reset(1,0,5);out=normalize_own_uid(api);assert(out.reason==4&&calls==1);
 for(int kind:{3,4,6,7}){reset(1,0,kind);out=normalize_own_uid(api);assert(out.reason==5&&calls==1);}
 std::puts("{\"status\":\"OWN_UID_SHARED_HELPER_TESTS_PASS\",\"cases\":13,\"console_contact\":false}");
}
