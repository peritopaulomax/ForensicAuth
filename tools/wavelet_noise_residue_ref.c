/*
 * Standalone reference for Peritus WaveletsNoiseResidue (filter.cpp + dwt.c).
 * Usage: wavelet_noise_residue_ref in.raw width height out.raw order blocksize thr post
 */
#ifndef max
#define max(a, b) (((a) > (b)) ? (a) : (b))
#endif

#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <opencv2/opencv.hpp>

extern "C" {
#include "dwt.h"
}

static void scaling_coefficients(int order, double *h) {
    switch (order) {
    case 8:
        h[0]=0.230377813309; h[1]=0.714846570553; h[2]=0.630880767930; h[3]=-0.027983769417;
        h[4]=-0.187034811719; h[5]=0.030841381836; h[6]=0.032883011667; h[7]=-0.010597401785;
        break;
    default:
        fprintf(stderr, "order %d not supported in ref\n", order);
        exit(2);
    }
}

static int cmpfunc(const void *a, const void *b) {
    double da = *(const double *)a;
    double db = *(const double *)b;
    if (da < db) return -1;
    if (da > db) return 1;
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 10) {
        fprintf(stderr, "usage: %s in.raw width height out.raw order blocksize thr post\n", argv[0]);
        return 1;
    }
    const char *in_path = argv[1];
    int imgWidth = atoi(argv[2]);
    int imgHeight = atoi(argv[3]);
    const char *out_path = argv[4];
    int order = atoi(argv[5]);
    int blocksize = atoi(argv[6]);
    int thr = atoi(argv[7]);
    int post = atoi(argv[8]);

    FILE *fin = fopen(in_path, "rb");
    if (!fin) { perror("fopen in"); return 1; }
    cv::Mat src(imgHeight, imgWidth, CV_8UC1);
    if ((int)fread(src.data, 1, imgHeight * imgWidth, fin) != imgHeight * imgWidth) {
        fprintf(stderr, "read size mismatch\n");
        return 1;
    }
    fclose(fin);

    double *entrada = new double[imgHeight * imgWidth];
    double *saida = new double[imgHeight * imgWidth];
    double *h = new double[order];
    scaling_coefficients(order, h);

    for (int i = 0; i < imgHeight * imgWidth; i++)
        entrada[i] = (double)src.data[i];

    dwtX(entrada, imgHeight, imgWidth, h, order, 1, saida);

    cv::Size imgSize((int)floor((double)imgWidth / (2 * blocksize)),
                     (int)floor((double)imgHeight / (2 * blocksize)));
    cv::Mat dest(imgSize.height, imgSize.width, CV_32FC1);
    float *pDest = dest.ptr<float>(0);

    double *dummy = new double[blocksize * blocksize];
    for (int i = 0; i < imgSize.height; i++) {
        for (int j = 0; j < imgSize.width; j++) {
            int n = 0;
            if (i * blocksize + imgSize.height + blocksize - 1 < imgHeight &&
                j * blocksize + imgSize.width + blocksize - 1 < imgWidth) {
                for (int k = 0; k < blocksize; k++) {
                    for (int l = 0; l < blocksize; l++) {
                        int ii = i * blocksize + imgHeight / 2 + k;
                        int jj = j * blocksize + imgWidth / 2 + l;
                        dummy[n++] = fabs(saida[ii * imgWidth + jj]);
                    }
                }
                qsort(dummy, blocksize * blocksize, sizeof(dummy[0]), cmpfunc);
                double valor;
                if (blocksize % 2)
                    valor = dummy[(blocksize * blocksize) / 2];
                else
                    valor = dummy[(blocksize * blocksize) / 2] / 2 + dummy[(blocksize * blocksize) / 2 + 1] / 2;
                pDest[i * imgSize.width + j] = (float)valor;
            }
        }
    }

    cv::resize(dest, dest, src.size(), 0, 0, cv::INTER_CUBIC);
    cv::normalize(dest, dest, 0, 255, cv::NORM_MINMAX, CV_8UC1);
    if (post) {
        dest = dest * 255 / thr;
        cv::normalize(dest, dest, 0, 255, cv::NORM_MINMAX, CV_8UC1);
    }
    cv::applyColorMap(dest, dest, cv::COLORMAP_JET);

    FILE *fout = fopen(out_path, "wb");
    if (!fout) { perror("fopen out"); return 1; }
    fwrite(dest.data, 1, imgHeight * imgWidth * 3, fout);
    fclose(fout);

    delete[] h;
    delete[] entrada;
    delete[] saida;
    delete[] dummy;
    return 0;
}
