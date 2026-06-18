// Minimal CopyMovePCA probe — mirrors Peritus filter.cpp through displacement voting.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <numeric>
#include <opencv2/opencv.hpp>
#include <vector>

static void vectorize(const cv::Mat& src, int b, cv::Mat& dados, int& linhas, int& colunas, int& nb) {
    linhas = src.rows;
    colunas = src.cols;
    int b2 = b * b;
    nb = (linhas - b + 1) * (colunas - b + 1);
    dados = cv::Mat::zeros(nb, b2, CV_32FC1);
    cv::Mat imagem;
    src.convertTo(imagem, CV_32FC1);
    if (!imagem.isContinuous()) imagem = imagem.clone();
    float* pImagem = imagem.ptr<float>(0);
    float* pDados = dados.ptr<float>(0);
    for (int i = 0; i < linhas - b + 1; i++) {
        for (int j = 0; j < colunas - b + 1; j++) {
            for (int k = 0; k < b; k++) {
                for (int h = 0; h < b; h++) {
                    pDados[(j * (linhas - b + 1) + i) * b2 + h * b + k] =
                        pImagem[(i + k) * colunas + j + h];
                }
            }
        }
    }
}

int main(int argc, char** argv) {
    if (argc < 2) return 1;
    cv::Mat src = cv::imread(argv[1], cv::IMREAD_GRAYSCALE);
    if (src.empty()) return 2;

    int b = 7;
    double nComp = 0.75;
    int Nn = 2, Q = 256, Nf = 128, Nd = 16;

    int linhas, colunas, Nb;
    cv::Mat dados;
    vectorize(src, b, dados, linhas, colunas, Nb);
    int b2 = b * b;
    int Nt = (int)std::round(dados.cols * nComp);

    cv::PCA data_pca(dados, cv::Mat(), cv::PCA::DATA_AS_ROW, Nt);
    cv::Mat G = cv::Mat::zeros(Nb, Nt, dados.type());
    for (int i = 0; i < Nb; i++) data_pca.project(dados.row(i), G.row(i));

    double minimoG, maximoG;
    cv::minMaxLoc(G, &minimoG, &maximoG);
    maximoG = std::floor(maximoG / Q);

    cv::Mat B = cv::Mat::zeros(1, Nb, CV_64FC1);
    double* pB = B.ptr<double>(0);
    float* pG = G.ptr<float>(0);
    for (int i = 0; i < Nb; i++) {
        for (int j = 0; j < Nt; j++) {
            pB[i] += std::pow(maximoG + 1, j) * std::floor(pG[i * Nt + j] / Q);
        }
    }

    std::vector<int> pIND(Nb);
    std::iota(pIND.begin(), pIND.end(), 0);
    std::sort(pIND.begin(), pIND.end(), [&](int i1, int i2) { return pB[i1] < pB[i2]; });

    int n_desloc = 0;
    std::vector<int> p_desloc;
    p_desloc.reserve(10000);
    int window = Nb - Nn + 1;
    int stride = linhas - b + 1;
    std::vector<int> MD(Nn * window, 0);
    std::vector<int> Dir((Nn - 1) * window, 0);
    int cont_size = 2 * (linhas * colunas - 1);
    std::vector<int> contador(cont_size, 0);

    for (int j = 0; j < window; j++) MD[j] = pIND[j];

    for (int i = 1; i < Nn; i++) {
        for (int j = 0; j < window; j++) {
            float maior, menor;
            int distancia;
            if (pIND[j + i] > MD[j]) {
                maior = (float)pIND[j + i];
                menor = (float)MD[j];
                Dir[(i - 1) * window + j] = 0;
            } else {
                menor = (float)pIND[j + i];
                maior = (float)MD[j];
                Dir[(i - 1) * window + j] = 1;
            }
            distancia = (int)std::abs(
                maior - menor + std::floor(menor / stride) * stride - std::floor(maior / stride) * stride);
            distancia += (int)(std::floor(maior / stride) - std::floor(menor / stride));

            if ((maior - std::floor(maior / stride) * stride) < (menor - std::floor(menor / stride) * stride)) {
                MD[i * window + j] = (int)menor - maior;
                if (distancia > Nd) {
                    int aux = (int)linhas * colunas - 1 + (int)maior - (int)menor;
                    contador[aux] += 1;
                    if (contador[aux] > Nf && n_desloc < 10000) {
                        p_desloc.push_back((int)menor - maior);
                        n_desloc++;
                    }
                }
            } else {
                MD[i * window + j] = (int)maior - menor;
                if (distancia > Nd) {
                    int aux = (int)maior - (int)menor;
                    contador[aux] += 1;
                    if (contador[aux] > Nf && n_desloc < 10000) {
                        p_desloc.push_back((int)maior - menor);
                        n_desloc++;
                    }
                }
            }
        }
    }

    std::cout << "Nb=" << Nb << " n_desloc=" << n_desloc << "\n";
    std::vector<int> uniq;
    for (int d : p_desloc) {
        if (uniq.empty() || uniq.back() != d) {
            bool seen = false;
            for (int u : uniq)
                if (u == d) seen = true;
            if (!seen) uniq.push_back(d);
        }
    }
    std::cout << "unique=" << uniq.size() << " values:";
    for (int u : uniq) std::cout << " " << u;
    std::cout << "\n";

    // Write colored mask like Peritus (unique displacements, morph)
    cv::Mat destR = cv::Mat::zeros(src.size(), CV_8U);
    cv::Mat destG = cv::Mat::zeros(src.size(), CV_8U);
    cv::Mat destB = cv::Mat::zeros(src.size(), CV_8U);

    std::vector<int> cList = {1, 8, 0, 255, 230, 230, 45, 54, 230, 230, 230, 155, 64};
    int cpos = 1;
    auto nextColor = [&]() {
        int rs = cList[cpos];
        cpos += 1;
        if (cpos > 54) cpos = 1;
        return rs;
    };

    std::vector<int> seen;
    for (int k = 0; k < n_desloc; k++) {
        int disp = p_desloc[k];
        bool already = false;
        for (int s : seen)
            if (s == disp) already = true;
        if (already) continue;
        seen.push_back(disp);

        int colorR = nextColor();
        int colorG = nextColor();
        int colorB = nextColor();
        for (int i = 1; i < Nn; i++) {
            for (int j = 0; j < window; j++) {
                if (MD[i * window + j] != disp) continue;
                int d = Dir[(i - 1) * window + j];
                int base = MD[j];
                int coord = base - d * std::abs(disp);
                int jj = (int)std::floor((double)coord / stride);
                int ii = coord - jj * stride;
                if (ii >= 0 && ii < linhas - b + 1 && jj >= 0 && jj < colunas - b + 1) {
                    destR.at<uchar>(ii, jj) = colorR;
                    destR.at<uchar>(ii + b - 1, jj + b - 1) = colorR;
                    destG.at<uchar>(ii, jj) = colorG;
                    destG.at<uchar>(ii + b - 1, jj + b - 1) = colorG;
                    destB.at<uchar>(ii, jj) = colorB;
                    destB.at<uchar>(ii + b - 1, jj + b - 1) = colorB;
                }
                coord = base + (1 - d) * std::abs(disp);
                jj = (int)std::floor((double)coord / stride);
                ii = coord - jj * stride;
                if (ii >= 0 && ii < linhas - b + 1 && jj >= 0 && jj < colunas - b + 1) {
                    destR.at<uchar>(ii, jj) = colorR;
                    destR.at<uchar>(ii + b - 1, jj + b - 1) = colorR;
                    destG.at<uchar>(ii, jj) = colorG;
                    destG.at<uchar>(ii + b - 1, jj + b - 1) = colorG;
                    destB.at<uchar>(ii, jj) = colorB;
                    destB.at<uchar>(ii + b - 1, jj + b - 1) = colorB;
                }
            }
        }
    }

    cv::Mat dest;
    cv::merge(std::vector<cv::Mat>{destB, destG, destR}, dest);
    int morph_size = b / 2;
    cv::Mat element = cv::getStructuringElement(
        cv::MORPH_ELLIPSE, cv::Size(2 * morph_size + 1, 2 * morph_size + 1),
        cv::Point(morph_size, morph_size));
    cv::morphologyEx(dest, dest, cv::MORPH_CLOSE, element);
    cv::morphologyEx(dest, dest, cv::MORPH_OPEN, element);

    std::string out = argc > 2 ? argv[2] : "/tmp/cm26_cpp_probe.png";
    cv::imwrite(out, dest);
    return 0;
}
