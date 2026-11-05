#define main renderer_previous_main
#include "present_test.cpp"
#undef main
#include <cassert>
extern "C" void omni_gpu_present_test_frame_cache(size_t*,uint64_t*,uint64_t*);

static size_t count(){size_t n;uint64_t i,h;omni_gpu_present_test_frame_cache(&n,&i,&h);return n;}
static uint64_t imports(){size_t n;uint64_t i,h;omni_gpu_present_test_frame_cache(&n,&i,&h);return i;}
static void show(Scene& s,int staging=0){std::vector<uint8_t> o;int r; s.frame[0]^=3; assert(s.present(s.w,s.h,o,staging,&r)==0);assert(o==s.canvas());}
int main(){
 {Scene a(320,180,false,1),b(320,180,false,2),c(320,180,false,3);
 show(a);show(b);assert(count()==2);auto n=imports();
 for(int i=0;i<120;i++)show(i%2?b:a);assert(imports()==n);assert(count()==2);
 show(c);assert(imports()==n+1);show(b);assert(imports()==n+1);show(a);assert(imports()==n+2);
 auto oldh=a.h;a.h=oldh-1;show(a);assert(imports()==n+3);a.h=oldh;show(a);assert(imports()==n+4);
 int unrelated;omni_gpu_present_forget(&unrelated);assert(count()==2);
 omni_gpu_present_forget(a.frame);assert(count()==0);show(a);show(b);assert(count()==2);
 omni_gpu_present_forget(b.frame);assert(count()==0);show(a,1);assert(count()==0);
 {Scene u(3840,2160,false,4),v(3840,2160,false,5);show(u);show(v);auto k=imports();for(int j=0;j<6;j++)show(j%2?v:u);assert(imports()==k);assert(count()==2);} assert(count()==0);
 // (injected import failure: needs Astra's instrumented copy; not in the shipped source)
 omni_gpu_present_forget(a.frame);omni_gpu_present_forget(c.frame);assert(count()==0);
 }
 long b,i,m;omni_gpu_present_test_teardown(&b,&i,&m);assert(!b&&!i&&!m);assert(count()==0);
 printf("PAIR PASS: 120 alternating exact frames, LRU, size replacement, forget, staging, teardown\n");
 return 0;
}

