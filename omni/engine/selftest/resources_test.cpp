// Check initial resource extraction and repair of a same-length corrupted CA file.
#include "OmniResources.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string>

int main()
{
    char directory[] = "/tmp/omni-resources-XXXXXX";
    assert(mkdtemp(directory));
    assert(omniInstallResources(directory) == 0);
    std::string ca = std::string(directory) + "/cacert.pem";
    FILE* stream = fopen(ca.c_str(), "r+b");
    assert(stream);
    int original = fgetc(stream);
    assert(original != EOF);
    rewind(stream);
    assert(fputc(original ^ 1, stream) != EOF);
    assert(fclose(stream) == 0);
    assert(omniInstallResources(directory) == 0);
    stream = fopen(ca.c_str(), "rb");
    assert(stream);
    assert(fgetc(stream) == original);
    fclose(stream);
    assert(omniInstallResources(directory) == 0);
    puts("Resource extraction, same-size repair and repeat install passed");
}
