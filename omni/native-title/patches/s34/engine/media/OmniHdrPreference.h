// SPDX-License-Identifier: GPL-3.0-or-later
// OMNI_HDR_PREFERENCE_V1. Fixed application-owned path; ordinary preference only.
#pragma once
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <string>
namespace OmniHdrPreference {
struct Value { unsigned revision=1;std::string mode="off";bool exists=false; };
static inline bool mode(const std::string& s){return s=="off"||s=="auto"||s=="on";}
static inline bool revision(const std::string& s,unsigned& out){
 if(s.empty()||s.size()>10)return false;
 unsigned long long n=0;
 for(char c:s){if(c<'0'||c>'9')return false;n=n*10+unsigned(c-'0');if(n>2147483646)return false;}
 if(!n)return false;
 out=unsigned(n);return true;
}
static inline bool read(const std::string& path,Value& out){
 FILE*f=fopen(path.c_str(),"rb");if(!f){if(errno==ENOENT){out=Value{};return true;}return false;}
 char b[65];const size_t n=fread(b,1,sizeof b,f);const bool error=ferror(f)!=0;fclose(f);
 if(error||!n||n>=sizeof b||b[n-1]!='\n')return false;
 std::string s(b,n-1);const size_t tab=s.find('\t');if(tab==std::string::npos)return false;
 Value v;if(!revision(s.substr(0,tab),v.revision)||!mode(s.substr(tab+1)))return false;
 v.mode=s.substr(tab+1);v.exists=true;out=v;return true;
}
enum Result { Saved, Invalid, Stale, Unavailable };
static inline Result write(const std::string& path,unsigned expected,const std::string& requested,Value& out){
 if(!mode(requested)||!expected||expected>=2147483646)return Invalid;
 Value current;if(!read(path,current))return Unavailable;if(current.revision!=expected)return Stale;
 const std::string tmp=path+".new",body=std::to_string(expected+1)+"\t"+requested+"\n";
 FILE*f=fopen(tmp.c_str(),"wb");if(!f)return Unavailable;
 bool ok=fwrite(body.data(),1,body.size(),f)==body.size();if(fflush(f)!=0)ok=false;if(fclose(f)!=0)ok=false;
 if(!ok){remove(tmp.c_str());return Unavailable;}if(rename(tmp.c_str(),path.c_str())!=0){remove(tmp.c_str());return Unavailable;}
 out={expected+1,requested,true};return Saved;
}
}
