#pragma once

#include <signal.h>
#include "shared/vmprof.h"

#define SINGLE_BUF_SIZE (8192 - 2 * sizeof(unsigned int))

#ifdef VMPROF_WINDOWS
#include "msiinttypes/inttypes.h"
#include "msiinttypes/stdint.h"
#else
#include <inttypes.h>
#include <stdint.h>
#endif

#ifndef RPY_EXTERN
#define RPY_EXTERN RPY_EXPORTED
#endif
#ifdef _WIN32
#ifndef RPY_EXPORTED
#define RPY_EXPORTED __declspec(dllexport)
#endif
#else
#define RPY_EXPORTED  extern __attribute__((visibility("default")))
#endif

RPY_EXTERN char *vmprof_init(int fd, double interval, int memory,
                     int lines, const char *interp_name, int native);
RPY_EXTERN void vmprof_ignore_signals(int);
RPY_EXTERN int vmprof_enable(int memory, int native);
RPY_EXTERN int vmprof_disable(void);
RPY_EXTERN int vmprof_register_virtual_function(char *, intptr_t, int);
RPY_EXTERN void* vmprof_stack_new(void);
RPY_EXTERN int vmprof_stack_append(void*, long);
RPY_EXTERN long vmprof_stack_pop(void*);
RPY_EXTERN void vmprof_stack_free(void*);
RPY_EXTERN intptr_t vmprof_get_traceback(void *, void *, intptr_t*, intptr_t);
/**
 * Registers the first argument as an evaluation function. The zero terminated
 * name is provided as argument. If NULL is provided,
 * it resets the eval functions.
 *
 * Note that a maximum of 5 evaluation functions is supported.
 *
 * Return 0 on success, any other value on failure.
 */
RPY_EXTERN int vmprof_register_eval(const char *);

long vmprof_write_header_for_jit_addr(intptr_t *result, long n,
                                      intptr_t addr, int max_depth);

#define RVMPROF_TRACEBACK_ESTIMATE_N(num_entries)  (2 * (num_entries) + 4)
