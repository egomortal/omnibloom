/* Private payload credential consistency only; changes only this process UID. */
#ifndef OMNI_OWN_UID_HPP
#define OMNI_OWN_UID_HPP
#include <sys/types.h>
#include <unistd.h>
struct OwnUidApi {
 uid_t (*real_uid)();uid_t (*effective_uid)();gid_t (*real_gid)();gid_t (*effective_gid)();
 int (*groups)(int,gid_t*);int (*set_uid)(uid_t);
};
struct OwnUidSnapshot {uid_t real_uid{},effective_uid{};gid_t real_gid{},effective_gid{};int group_count{-1};gid_t groups[32]{};};
struct OwnUidResult {OwnUidSnapshot before{},after{};bool attempted{false},groups_unchanged{false};int setuid_result{-1};int reason{1};};
static inline bool own_uid_snapshot(const OwnUidApi& api,OwnUidSnapshot& out) {
 out.real_uid=api.real_uid();out.effective_uid=api.effective_uid();out.real_gid=api.real_gid();out.effective_gid=api.effective_gid();
 out.group_count=api.groups(32,out.groups);return out.group_count>=0&&out.group_count<=32;
}
static inline OwnUidResult normalize_own_uid(const OwnUidApi& api) {
 OwnUidResult out{};
 if(!own_uid_snapshot(api,out.before)){out.reason=1;return out;}
 if(out.before.effective_uid!=0||(out.before.real_uid!=0&&out.before.real_uid!=1)){out.reason=2;return out;}
 if(out.before.real_uid==1){out.attempted=true;out.setuid_result=api.set_uid(out.before.effective_uid);if(out.setuid_result!=0){out.reason=3;return out;}}
 if(!own_uid_snapshot(api,out.after)){out.reason=4;return out;}
 out.groups_unchanged=out.before.group_count==out.after.group_count;
 if(out.groups_unchanged)for(int i=0;i<out.before.group_count;++i)if(out.before.groups[i]!=out.after.groups[i])out.groups_unchanged=false;
 if(out.after.real_uid!=0||out.after.effective_uid!=0||out.before.real_gid!=out.after.real_gid||out.before.effective_gid!=out.after.effective_gid||!out.groups_unchanged){out.reason=5;return out;}
 out.reason=0;return out;
}
#endif
