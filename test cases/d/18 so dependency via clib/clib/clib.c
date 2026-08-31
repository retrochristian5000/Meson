#include "clib.h"
#include <libxml2/libxml/xmlversion.h>
#include <exampleshlib.h>

void clib_call_blkid(void) {
    exampleshlib_hello();
    LIBXML_TEST_VERSION
}
