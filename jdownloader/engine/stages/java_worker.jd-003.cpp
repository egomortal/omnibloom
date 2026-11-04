/* SPDX-License-Identifier: GPL-3.0-or-later
 * Standalone hbldr worker. The Omni renderer is never linked into this process.
 */
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <fcntl.h>
#include <dirent.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include "jni.h"
#include "native_trace.hpp"
using Initializer=void (*)();
extern "C" Initializer __jvm_init_array_start[],__jvm_init_array_end[];
static const char root[]="/data/omni-downloader/jdownloader/";
static const char image[]="/data/omni-downloader/jdownloader/native/java25";
static char session[33],install[129],receipt[1024],mode_name[20];
static FILE *native_log=nullptr;
static std::atomic_flag receipt_written=ATOMIC_FLAG_INIT;
static std::atomic<bool> startup_complete{false},worker_complete{false};
static unsigned maximum_seconds=3600;
static unsigned startup_limit_seconds=180;
static int receipt_fd=-1;
static char startup_timeout_report[1800],worker_timeout_report[1800];
static size_t startup_timeout_size=0,worker_timeout_size=0;
static uint64_t native_started_us=0;
extern "C" uint64_t sceKernelGetProcessTime();
extern "C" int sceKernelUsleep(uint32_t);
extern "C" int64_t sceKernelWrite(int,const void*,size_t);
extern "C" int sceKernelFsync(int);
extern "C" int __real_pthread_create(pthread_t*,const pthread_attr_t*,void*(*)(void*),void*);
static void phase(const char* name) {
 if(!native_log)return;
 uint64_t now=sceKernelGetProcessTime();
 std::fprintf(native_log,"phase=%s elapsed_us=%llu\n",name,static_cast<unsigned long long>(now>=native_started_us?now-native_started_us:0));
 std::fflush(native_log);
}

static bool beneath(const char* value) {
 if(std::strncmp(value,root,sizeof(root)-1)!=0||std::strlen(value)>=1000)return false;
 for(const char* p=value;*p;++p) if(*p=='\\'||*p=='"'||static_cast<unsigned char>(*p)<32)return false;
 return !std::strstr(value,"/../")&&!std::strstr(value,"/./")&&!std::strstr(value,"//")&&!std::strstr(value,"/..");
}
// The parent creates a trusted small JSON configuration. Parse only the native
// string properties, reject duplicates/escapes, and let the real Java bridge
// validate its complete schema. Never log configuration text or token.
static bool field(const char* json,const char* name,char* out,size_t capacity) {
 char needle[96];if(std::snprintf(needle,sizeof(needle),"\"%s\"",name)<=0)return false;
 const char* p=std::strstr(json,needle);if(!p||std::strstr(p+std::strlen(needle),needle))return false;
 p+=std::strlen(needle);while(*p==' '||*p=='\t'||*p=='\r'||*p=='\n')++p;
 if(*p++!=':')return false;
 while(*p==' '||*p=='\t'||*p=='\r'||*p=='\n')++p;
 if(*p++!='"')return false;
 size_t n=0;
 while(*p&&*p!='"') {if(*p=='\\'||static_cast<unsigned char>(*p)<32||n+1>=capacity)return false;out[n++]=*p++;}
 out[n]=0;return *p=='"'&&n>0;
}
static void finish(int code,const char* phase) {
 if(!receipt[0]||receipt_written.test_and_set())return;
 char report[1800];int n=std::snprintf(report,sizeof(report),"{\"schema\":\"omni-java-native/v1\",\"session\":\"%s\",\"install_id\":\"%s\",\"native_pid\":%d,\"mode\":\"%s\",\"finished\":true,\"exit_code\":%d,\"phase\":\"%s\"}\n",session,install,getpid(),mode_name,code,phase);
 if(n<=0||static_cast<size_t>(n)>=sizeof(report))return;
 int fd=receipt_fd;if(fd<0)return;
 size_t written=0;while(written<static_cast<size_t>(n)){ssize_t rc=write(fd,report+written,n-written);if(rc<0&&errno==EINTR)continue;if(rc<=0)break;written+=static_cast<size_t>(rc);}
 fsync(fd);close(fd);receipt_fd=-1;worker_complete.store(true);
}
static int vm_print(FILE*,const char* format,va_list arguments) {
 if(!native_log)return 0;
 int n=std::vfprintf(native_log,format,arguments);std::fflush(native_log);return n;
}
static void vm_exit(int code) {finish(code,"vm-exit-callback");}
static void vm_abort() {finish(70,"vm-abort-callback");}
static void* watchdog(void*) {
 const uint64_t begin=sceKernelGetProcessTime();
 while(!worker_complete.load()) {
  const uint64_t now=sceKernelGetProcessTime();
  const uint64_t limit=startup_complete.load()?maximum_seconds+180u:startup_limit_seconds;
  if(now<begin||now-begin>limit*1000000ull) {
   if(!receipt_written.test_and_set()) {
    const bool started=startup_complete.load();const char* report=started?worker_timeout_report:startup_timeout_report;
    const size_t size=started?worker_timeout_size:startup_timeout_size;
    // No allocator, locale, stdio, VM trace, or compiler-TLS operations here.
    size_t done=0;while(done<size){int64_t n=sceKernelWrite(receipt_fd,report+done,size-done);if(n<=0)break;done+=static_cast<size_t>(n);}
    sceKernelFsync(receipt_fd);
   }
   __real__exit(124);
  }
  sceKernelUsleep(100000);
 }
 return nullptr;
}
static bool identity_ok() {
 if(std::strlen(session)!=32||std::strlen(install)>128)return false;
 for(const char* p=session;*p;++p)if(!(*p>='0'&&*p<='9')&&!(*p>='a'&&*p<='f'))return false;
 for(const char* p=install;*p;++p)if(!(*p>='0'&&*p<='9')&&!(*p>='a'&&*p<='z')&&!(*p>='A'&&*p<='Z')&&*p!='.'&&*p!='_'&&*p!='-')return false;
 return true;
}
static bool append(char* output,size_t capacity,const char* value) {
 size_t a=std::strlen(output),b=std::strlen(value);if(a+b+1>capacity)return false;
 std::memcpy(output+a,value,b+1);return true;
}
static int compare_names(const void* a,const void* b){return std::strcmp(static_cast<const char*>(a),static_cast<const char*>(b));}
static bool append_jars(char* output,size_t capacity,const char* directory) {
 DIR* dir=opendir(directory);if(!dir)return errno==ENOENT;
 char names[128][256];size_t count=0;bool valid=true;errno=0;
 while(dirent* entry=readdir(dir)) {
  size_t n=std::strlen(entry->d_name);if(n<4||std::strcmp(entry->d_name+n-4,".jar"))continue;
  if(count==128||n>=256||std::strchr(entry->d_name,':')||std::strchr(entry->d_name,'/')||std::strchr(entry->d_name,'\\')){valid=false;break;}
  std::memcpy(names[count++],entry->d_name,n+1);
 }
 if(errno)valid=false;closedir(dir);if(!valid)return false;
 std::qsort(names,count,sizeof(names[0]),compare_names);
 for(size_t i=0;i<count;++i)if(!append(output,capacity,":")||!append(output,capacity,directory)||!append(output,capacity,"/")||!append(output,capacity,names[i]))return false;
 return true;
}
int main(int argc,char** argv) {
 if(argc!=3||!beneath(argv[1])||(std::strcmp(argv[2],"hello")&&std::strcmp(argv[2],"providers")&&std::strcmp(argv[2],"watchdog")&&std::strcmp(argv[2],"jdownloader")))return 2;
 std::snprintf(mode_name,sizeof(mode_name),"%s",argv[2]);
 char config[8193]{};FILE* input=std::fopen(argv[1],"rb");if(!input)return 3;
 size_t size=std::fread(config,1,sizeof(config)-1,input);bool bad=std::ferror(input)||std::fgetc(input)!=EOF;std::fclose(input);
 if(bad||size==0)return 4;
 char runtime[1024],home[1024],tmp[1024],java_home[1024];
 if(!field(config,"session",session,sizeof(session))||!field(config,"install_id",install,sizeof(install))||!identity_ok()||
    !field(config,"native_receipt_file",receipt,sizeof(receipt))||!beneath(receipt)||
    !field(config,"runtime",runtime,sizeof(runtime))||!beneath(runtime)||
    !field(config,"home",home,sizeof(home))||!beneath(home)||
    !field(config,"tmp",tmp,sizeof(tmp))||!beneath(tmp)||
    !field(config,"java_home",java_home,sizeof(java_home))||std::strcmp(java_home,image))return 5;
 char log_path[1100];std::snprintf(log_path,sizeof(log_path),"%s.log",receipt);
 int log_fd=open(log_path,O_WRONLY|O_CREAT|O_EXCL,0600);if(log_fd<0){finish(6,"log-open");return 6;}
 native_log=fdopen(log_fd,"w");if(!native_log){close(log_fd);finish(6,"log-stream");return 6;}
 native_started_us=sceKernelGetProcessTime();phase("native-log-open");
 receipt_fd=open(receipt,O_WRONLY|O_CREAT|O_EXCL,0600);if(receipt_fd<0)return 16;
 startup_timeout_size=static_cast<size_t>(std::snprintf(startup_timeout_report,sizeof(startup_timeout_report),"{\"schema\":\"omni-java-native/v1\",\"session\":\"%s\",\"install_id\":\"%s\",\"native_pid\":%d,\"mode\":\"%s\",\"finished\":true,\"exit_code\":124,\"phase\":\"VM-startup-deadline\"}\n",session,install,getpid(),mode_name));
 worker_timeout_size=static_cast<size_t>(std::snprintf(worker_timeout_report,sizeof(worker_timeout_report),"{\"schema\":\"omni-java-native/v1\",\"session\":\"%s\",\"install_id\":\"%s\",\"native_pid\":%d,\"mode\":\"%s\",\"finished\":true,\"exit_code\":124,\"phase\":\"worker-deadline\"}\n",session,install,getpid(),mode_name));
 if(startup_timeout_size>=sizeof(startup_timeout_report)||worker_timeout_size>=sizeof(worker_timeout_report)){finish(17,"watchdog-report-size");return 17;}
 const char* seconds=std::strstr(config,"\"max_seconds\"");
 if(seconds){seconds=std::strchr(seconds,':');if(seconds){char* end=nullptr;unsigned long n=std::strtoul(seconds+1,&end,10);if(n>=5&&n<=86400)maximum_seconds=static_cast<unsigned>(n);}}
 startup_limit_seconds=!std::strcmp(mode_name,"watchdog")?5u:180u;
 pthread_t guard{};int guard_code=__real_pthread_create(&guard,nullptr,watchdog,nullptr);
 if(guard_code){finish(14,"watchdog-thread-create");return 14;}
 if(pthread_detach(guard)){finish(15,"watchdog-thread-detach");return 15;}
 if(!std::strcmp(mode_name,"watchdog"))for(;;)sceKernelUsleep(100000);
 std::fprintf(native_log,"native pid=%d session=%s mode=%s\n",getpid(),session,mode_name);std::fflush(native_log);
 char image_path[1024];std::snprintf(image_path,sizeof(image_path),"%s/lib/modules",image);
 FILE* modules=std::fopen(image_path,"rb");unsigned char magic[4]{};size_t got=modules?std::fread(magic,1,4,modules):0;if(modules)std::fclose(modules);
 const unsigned char expected[4]={0xda,0xda,0xfe,0xca};
 if(got!=4||std::memcmp(magic,expected,4)){finish(7,"image-preflight");return 7;}
 std::fprintf(native_log,"begin explicit runtime constructors\n");std::fflush(native_log);
 for(auto* fn=__jvm_init_array_start;fn!=__jvm_init_array_end;++fn)if(*fn)(*fn)();
 std::fprintf(native_log,"runtime constructors completed\n");std::fflush(native_log);
 phase("constructors-complete");
 char classpath[6200],root_option[1100],home_option[1100],tmp_option[1100],pid_option[100],error_option[1200],jar_directory[1100],provider_option[1200];
 std::snprintf(classpath,sizeof(classpath),"-Djava.class.path=%s/classes:%s/Core.jar:%s/JDownloader.jar",runtime,runtime,runtime);
 std::snprintf(jar_directory,sizeof(jar_directory),"%s/libs",runtime);
 bool classpath_ok=append_jars(classpath,sizeof(classpath),jar_directory);
 std::snprintf(jar_directory,sizeof(jar_directory),"%s/extensions",runtime);
 classpath_ok=classpath_ok&&append_jars(classpath,sizeof(classpath),jar_directory)&&append(classpath,sizeof(classpath),":")&&append(classpath,sizeof(classpath),runtime)&&append(classpath,sizeof(classpath),":")&&append(classpath,sizeof(classpath),image)&&append(classpath,sizeof(classpath),"/classes");
 if(!classpath_ok){finish(8,"classpath-expansion");return 8;}
 std::snprintf(root_option,sizeof(root_option),"-DROOT=%s",runtime);
 std::snprintf(home_option,sizeof(home_option),"-Duser.home=%s",home);
 std::snprintf(tmp_option,sizeof(tmp_option),"-Djava.io.tmpdir=%s",tmp);
 std::snprintf(pid_option,sizeof(pid_option),"-Domni.jd.nativePid=%d",getpid());
 std::snprintf(error_option,sizeof(error_option),"-XX:ErrorFile=%s.hs-error.log",receipt);
 std::snprintf(provider_option,sizeof(provider_option),"-Domni.jd.providerReport=%s.provider.json",receipt);
 JavaVMOption options[]={
  {const_cast<char*>("-Xint"),nullptr},{const_cast<char*>("-XX:UseAVX=0"),nullptr},{const_cast<char*>("-XX:UseSSE=2"),nullptr},
  {const_cast<char*>("-Xms16m"),nullptr},{const_cast<char*>("-Xmx256m"),nullptr},{const_cast<char*>("-XX:CompressedClassSpaceSize=32m"),nullptr},
  {const_cast<char*>("-Xshare:off"),nullptr},{const_cast<char*>("-XX:+UseSerialGC"),nullptr},{const_cast<char*>("-XX:ActiveProcessorCount=2"),nullptr},
  {const_cast<char*>("-XX:-UsePerfData"),nullptr},{const_cast<char*>("-Djava.awt.headless=true"),nullptr},{const_cast<char*>("-Duser.timezone=UTC"),nullptr},
  {classpath,nullptr},{root_option,nullptr},{home_option,nullptr},{tmp_option,nullptr},{pid_option,nullptr},{error_option,nullptr},{provider_option,nullptr},
  {const_cast<char*>("vfprintf"),reinterpret_cast<void*>(&vm_print)},{const_cast<char*>("exit"),reinterpret_cast<void*>(&vm_exit)},
  {const_cast<char*>("abort"),reinterpret_cast<void*>(&vm_abort)}};
 JavaVMInitArgs args{};args.version=JNI_VERSION_24;args.options=options;args.nOptions=sizeof(options)/sizeof(options[0]);args.ignoreUnrecognized=JNI_FALSE;
 JavaVM* vm=nullptr;JNIEnv* env=nullptr;
 phase("JNI-CreateJavaVM-enter");
 ps5_native_trace::enable();ps5_native_trace::quiet();int code=JNI_CreateJavaVM(&vm,reinterpret_cast<void**>(&env),&args);
 phase("JNI-CreateJavaVM-return");
 if(code!=JNI_OK||!vm||!env){finish(10,"JNI-CreateJavaVM");return 10;}
 startup_complete.store(true);
 const char* main_class=!std::strcmp(mode_name,"hello")?"Hello25":!std::strcmp(mode_name,"providers")?"NativeProviderProbe":"OmniJDownloaderBridge";
 phase("Java-class-lookup-enter");
 jclass klass=env->FindClass(main_class);jmethodID method=klass?env->GetStaticMethodID(klass,"main","([Ljava/lang/String;)V"):nullptr;
 jclass string_type=env->FindClass("java/lang/String");
 jobjectArray arguments=string_type?env->NewObjectArray(!std::strcmp(mode_name,"jdownloader")?1:0,string_type,nullptr):nullptr;
 if(arguments&&!std::strcmp(mode_name,"jdownloader")){jstring path=env->NewStringUTF(argv[1]);if(path){env->SetObjectArrayElement(arguments,0,path);env->DeleteLocalRef(path);}}
 bool failed=env->ExceptionCheck()||!klass||!method||!arguments;
 phase("Java-class-lookup-return");
 if(!failed){phase("Java-main-enter");env->CallStaticVoidMethod(klass,method,arguments);failed=env->ExceptionCheck();phase("Java-main-return");}
 if(failed){env->ExceptionDescribe();env->ExceptionClear();}
 if(arguments)env->DeleteLocalRef(arguments);if(string_type)env->DeleteLocalRef(string_type);if(klass)env->DeleteLocalRef(klass);
 phase("DestroyJavaVM-enter");int destroyed=vm->DestroyJavaVM();ps5_native_trace::disable();phase("DestroyJavaVM-return");
 code=failed?11:destroyed==JNI_OK?0:12;finish(code,failed?"Java-main-exception":destroyed==JNI_OK?"Java-main-and-destroy-complete":"DestroyJavaVM");
 worker_complete.store(true);std::fclose(native_log);return code;
}
