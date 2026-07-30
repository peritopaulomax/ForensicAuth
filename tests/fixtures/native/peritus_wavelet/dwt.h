#ifndef DWT_H
#define DWT_H
#include "rwt_platform.h"

#ifdef __cplusplus
extern "C" {
#endif


void dwt_convolution(double *, size_t, double *, double *, int, double *, double);

void dwt_allocate(size_t, size_t, int, double **, double **, double **, double **, double **);

void dwt_free(double **, double **, double **, double **, double **);

void dwt_coefficients(int , double *, double **, double **);

void dwtX(double *, size_t, size_t, double *, int, int, double *);

#ifdef __cplusplus
}
#endif

#endif
