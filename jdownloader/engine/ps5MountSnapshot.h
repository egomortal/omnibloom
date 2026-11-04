/* Bounded real kernel mount snapshots. The caller owns the returned array. */
#ifndef OMNI_PS5_MOUNT_SNAPSHOT_H
#define OMNI_PS5_MOUNT_SNAPSHOT_H
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#ifndef PS5_MOUNT_ALLOC
#define PS5_MOUNT_ALLOC malloc
#define PS5_MOUNT_FREE free
#endif
static int ps5_mount_snapshot(int (*query)(struct statfs*,long,int),struct statfs** output,int* count) {
 *output=NULL;*count=0;
 for(int attempt=0;attempt<8;++attempt){
  int observed=query(NULL,0,MNT_NOWAIT);if(observed<0)return -1;
  if(observed>4096){errno=EOVERFLOW;return -1;}
  if(observed==0)return 0;
  size_t capacity=(size_t)observed;if(capacity<=4080)capacity+=16;else capacity=4096;
  if(capacity>SIZE_MAX/sizeof(struct statfs)){errno=EOVERFLOW;return -1;}
  struct statfs* entries=(struct statfs*)PS5_MOUNT_ALLOC(capacity*sizeof(struct statfs));if(entries==NULL){errno=ENOMEM;return -1;}
  int copied=query(entries,(long)(capacity*sizeof(struct statfs)),MNT_NOWAIT);if(copied<0){int error=errno;PS5_MOUNT_FREE(entries);errno=error;return -1;}
  int after=query(NULL,0,MNT_NOWAIT);if(after<0){int error=errno;PS5_MOUNT_FREE(entries);errno=error;return -1;}
  if((size_t)copied<=capacity&&(size_t)after<=capacity&&copied==after){*output=entries;*count=copied;return 0;}
  PS5_MOUNT_FREE(entries);
 }
 errno=EAGAIN;return -1;
}
#endif
