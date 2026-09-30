#pragma once
#include <cstdint>
namespace nn {
struct Result {
    unsigned value;
    bool isSuccess() const { return value == 0; }
};
namespace fs {
struct FileHandle { uint64_t value; };
constexpr int OpenMode_Read = 1;
Result MountSdCardForDebug(const char*);
Result OpenFile(FileHandle*, const char*, int);
Result GetFileSize(long*, FileHandle);
Result ReadFile(FileHandle, long, void*, unsigned long);
void CloseFile(FileHandle);
}
}
