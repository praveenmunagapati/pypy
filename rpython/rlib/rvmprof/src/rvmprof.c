#define _GNU_SOURCE 1

#ifdef VMPROF_UNIX
#include <dlfcn.h>
#endif

#ifdef RPYTHON_LL2CTYPES
   /* only for testing: ll2ctypes sets RPY_EXTERN from the command-line */

#else
#  include "common_header.h"
#  include "structdef.h"
#  include "src/threadlocal.h"
#  include "rvmprof.h"
#  include "forwarddecl.h"
#endif



#include "shared/vmprof_get_custom_offset.h"
#ifdef VMPROF_UNIX
#include "shared/vmprof_main.h"
#else
#include "shared/vmprof_main_win32.h"
#endif

int _vmprof_eval_count = 0;
void * _vmprof_eval_funcs[5];

int vmprof_register_eval(const char * name)
{
#ifdef VMPROF_UNIX
    void * func = NULL;

    if (_vmprof_eval_count >= 5) {
        fprintf(stderr, "WARNING: cannot register more than 5 rpython interpreter " \
                        "evaluation functions (you can increase the amount in rvmprof.c)\n");
        return -1;
    }
    if (name == NULL) { 
        _vmprof_eval_count = 0;
    } else {
        func = dlsym(RTLD_DEFAULT, name);
        if (func == NULL) {
            fprintf(stderr, "WARNING: could not lookup addr of '%s', dlsym returned NULL\n", name);
            return -1;
        }
        _vmprof_eval_funcs[_vmprof_eval_count++] = func;
    }
#endif
    return 0;
}

int IS_VMPROF_EVAL(void * ptr)
{
    int i = 0;
    for (i = 0; i < _vmprof_eval_count; i++) {
        if (ptr == _vmprof_eval_funcs[i]) {
            return 1;
        }
    }
    return 0;
}
