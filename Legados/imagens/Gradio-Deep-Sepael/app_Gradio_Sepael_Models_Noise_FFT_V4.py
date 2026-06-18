# -*- coding: utf-8 -*-

import os
import json
import logging
import pickle
import math
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import io
import random

import numpy as np
import pandas as pd
import torch
import joblib
import xgboost as xgb
from PIL import Image
import gradio as gr
from transformers import (
    AutoFeatureExtractor,
    AutoModelForImageClassification,
    pipeline
)
from torchvision import transforms
import cv2
from scipy import ndimage
from sklearn.linear_model import LogisticRegression

from scipy.signal import correlate2d
from scipy.stats import skew, kurtosis
from skimage.feature import graycomatrix, graycoprops
from skimage.measure import shannon_entropy, block_reduce
import torch.nn as nn
from torch.nn import functional as F
from torchvision.models import resnet50

# ==============================================================================
# SEÇÃO 1: CONFIGURAÇÕES GERAIS E DO AMBIENTE
# ==============================================================================
# (Esta seção permanece a mesma, apenas removi o path do model3_lr que não é mais usado)
for proxy_var in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(proxy_var, None)
os.environ['TRANSFORMERS_OFFLINE'] = '1'
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
os.environ['GRADIO_ANALYTICS_ENABLED'] = 'False'
os.environ['HF_HUB_CACHE'] = './models'
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
logger.info(f"✅ Usando device: {device}")

PIPELINE_CONFIG = {"use_models": ["model_1", "model_4", "model_8a"], "fft_feature_groups": {"texture": True}}
MODEL_PATHS = {"model_1": "haywoodsloan/ai-image-detector-deploy", "model_4": "cmckinle/sdxl-flux-detector_v1.1", "model_8a": "Custom/NPR_CVPR2024_vA"}
CLASS_NAMES = {"model_1": ['artificial', 'real'], "model_4": ['AI', 'Real'], "model_8a": ['Fake Image', 'Real Image']}
SCRIPT_DIR = Path(__file__).resolve().parent
MODEL1_XGB_FFT_PATH = SCRIPT_DIR / 'model1_xgboost_1p_20250809_213811.json'
MODEL2_XGB_AGG_PATH = SCRIPT_DIR / 'model2_xgboost_1p_20250809_213811.json'
NPR_WEIGHTS_PATH_A = SCRIPT_DIR / 'model_epoch_last_3090.pth'

# ==============================================================================
# SEÇÃO 2: LÓGICA DE PROCESSAMENTO DE IMAGEM E IA
# ==============================================================================
# (As funções auxiliares como seed_torch, softmax, a classe ResidueFFTFeatureExtractor, genELA,
# create_and_load_npr_model e predict_npr_unified permanecem as mesmas)

def seed_torch(seed=100):
    random.seed(seed); os.environ['PYTHONHASHSEED'] = str(seed); np.random.seed(seed)
    torch.manual_seed(seed); torch.cuda.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False; torch.backends.cudnn.deterministic = True; torch.backends.cudnn.enabled = False
seed_torch(100)

def softmax(x: np.ndarray) -> np.ndarray:
    exp_x = np.exp(x - np.max(x)); return exp_x / np.sum(exp_x)

class ResidueFFTFeatureExtractor:
    def __init__(self, config):
        self.config = config["fft_feature_groups"]; self.TOTAL_FEATURES = 30 if self.config.get("texture") else 0
        self.npr_transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    def _calculate_residues(self, i):
        r={};m=cv2.medianBlur(i,5);r['median']=i.astype(np.float32)-m.astype(np.float32)
        try:
            s=np.mean(cv2.estimateGaussNoise(i)) if hasattr(cv2,'estimateGaussNoise') else 10.0;h=np.clip(0.8*s,5.,25.)
            n=cv2.fastNlMeansDenoising(i,None,h=h,templateWindowSize=7,searchWindowSize=21);r['non_local_means']=i.astype(np.float32)-n.astype(np.float32)
        except Exception:
            g=cv2.GaussianBlur(i,(5,5),sigmaX=1.5);r['non_local_means']=i.astype(np.float32)-g.astype(np.float32)
        return r
    def _calculate_npr_residue_raw(self, image: Image.Image) -> np.ndarray:
        img_tensor = self.npr_transform(image.convert('RGB')).unsqueeze(0)
        _, c, w, h = img_tensor.shape
        if w % 2 == 1: img_tensor = img_tensor[:, :, :-1, :]
        if h % 2 == 1: img_tensor = img_tensor[:, :, :, :-1]
        interpolated = F.interpolate(F.interpolate(img_tensor, scale_factor=0.5, mode='nearest', recompute_scale_factor=True), 
                                   scale_factor=2.0, mode='nearest', recompute_scale_factor=True)
        npr_tensor = img_tensor - interpolated
        npr_np = npr_tensor.squeeze(0).permute(1, 2, 0).cpu().numpy()
        npr_gray = cv2.cvtColor(npr_np, cv2.COLOR_RGB2GRAY) if npr_np.shape[2] == 3 else npr_np.squeeze()
        return npr_gray
    def _process_fft(self, residue):
        if np.all(residue == 0): return np.zeros_like(residue, dtype=np.float32)
        fft = np.fft.fft2(residue); fft_shifted = np.fft.fftshift(fft); magnitude = np.abs(fft_shifted)
        rows, cols = residue.shape; crow, ccol = rows // 2 , cols // 2; magnitude[crow, ccol] = 0
        magnitude_log = np.log1p(magnitude); min_val, max_val = np.min(magnitude_log), np.max(magnitude_log)
        if max_val > min_val: magnitude_log = (magnitude_log - min_val) / (max_val - min_val)
        return magnitude_log
    def _extract_texture_features(self,m):
        q=(m*255).astype(np.uint8);g=graycomatrix(q,[1],[0,np.pi/4,np.pi/2,3*np.pi/4],256,True,True)
        return np.array([shannon_entropy(m),np.mean(graycoprops(g,'contrast')),np.mean(graycoprops(g,'homogeneity')),np.mean(graycoprops(g,'energy')),np.mean(graycoprops(g,'correlation'))])
    def extract_ensemble_fft_features(self,i):
        if not self.config.get("texture"):return np.array([])
        try:
            g=np.array(i.convert('L'));s,f,a=[1.,.5,.25],['median','non_local_means'],[]
            for sc in s:
                h,w=g.shape;si=cv2.resize(g,(int(w*sc),int(h*sc)),interpolation=cv2.INTER_AREA) if sc!=1. else g
                rs=self._calculate_residues(si)
                for fn in f:
                    ml=self._process_fft(rs[fn]);ft=self._extract_texture_features(ml);a.append(ft)
            return np.concatenate(a,dtype=np.float32)
        except Exception as e:
            logger.error(f"Erro em extract_ensemble_fft_features: {e}",exc_info=False);return np.zeros(self.TOTAL_FEATURES,dtype=np.float32)
    def generate_visualizations(self, image: Image.Image):
        try:
            g=np.array(image.convert('L'));r=self._calculate_residues(g)
            nr,mr=r.get('non_local_means',np.zeros_like(g,dtype=np.float32)),r.get('median',np.zeros_like(g,dtype=np.float32))
            npr=self._calculate_npr_residue_raw(image)
            def visualize(ra):
                n=cv2.normalize(ra,None,0,255,cv2.NORM_MINMAX,cv2.CV_8U);e=cv2.equalizeHist(n);return Image.fromarray(e)
            nrv,mrv,nprv=visualize(nr),visualize(mr),visualize(npr)
            nfv,mfv,npfv=visualize(self._process_fft(nr)),visualize(self._process_fft(mr)),visualize(self._process_fft(npr))
            return nrv,mrv,nprv,nfv,mfv,npfv
        except Exception as e:
            logger.error(f"Erro ao gerar visualizações: {e}");d=Image.new('L',(224,224),0);return d,d,d,d,d,d

def genELA(image, quality=80):
    try:
        img_copy=image.copy()
        if img_copy.mode!='RGB':img_copy=img_copy.convert('RGB')
        b=io.BytesIO();img_copy.save(b,format='JPEG',quality=quality);b.seek(0)
        try:c=Image.open(b)
        except Exception:return Image.new('RGB',img_copy.size,color='black')
        d=np.abs(np.array(img_copy,dtype=np.float32)-np.array(c,dtype=np.float32));ds=np.clip(d*20,0,255)
        return Image.fromarray(ds.astype(np.uint8))
    except Exception as e:
        logger.error(f"Erro ELA: {e}");return Image.new('RGB',(224,224),color='black')

def create_and_load_npr_model(p):
    if not os.path.exists(p):raise FileNotFoundError(f"Arquivo de pesos '{p}' não encontrado!")
    m=resnet50();m.fc1=nn.Linear(512,1);m.conv1=nn.Conv2d(3,64,3,2,1,bias=False);del m.layer3,m.layer4,m.fc
    s=torch.load(p,map_location='cpu')
    if all(k.startswith('module.')for k in s.keys()):
        from collections import OrderedDict
        s=OrderedDict([(k[7:],v)for k,v in s.items()])
    m.load_state_dict(s,strict=True);logger.info(f"✅ Pesos NPR de '{p}' carregados.")
    return m

def predict_npr_unified(image, model):
    trans=transforms.Compose([transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])])
    it=trans(image.convert('RGB')).unsqueeze(0)
    _,c,w,h=it.shape
    if w%2==1:it=it[:,:,:-1,:]
    if h%2==1:it=it[:,:,:,:-1]
    interp=F.interpolate(F.interpolate(it,scale_factor=.5,mode='nearest',recompute_scale_factor=True),scale_factor=2.,mode='nearest',recompute_scale_factor=True)
    nt=(it-interp)
    with torch.no_grad():
        x=model.conv1(nt*2./3.);x=model.bn1(x);x=model.relu(x);x=model.maxpool(x)
        x=model.layer1(x);x=model.layer2(x).mean((2,3),keepdim=False);x=model.fc1(x)
        p=x.sigmoid().cpu().numpy()[0][0]
    return {'Fake Image':float(p),'Real Image':1.-float(p)}

# ==============================================================================
# SEÇÃO 3: LÓGICA DE PREDIÇÃO E CARREGAMENTO
# ==============================================================================
def load_all_detection_models():
    # (Função permanece a mesma)
    m={};logger.info("🚀 Carregando modelos de detecção base...")
    for mid in PIPELINE_CONFIG["use_models"]:
        try:
            if mid=="model_8a":m[mid]={"model":create_and_load_npr_model(NPR_WEIGHTS_PATH_A),"type":"custom_npr"}
            elif mid=="model_4":
                e=AutoFeatureExtractor.from_pretrained(MODEL_PATHS[mid]);md=AutoModelForImageClassification.from_pretrained(MODEL_PATHS[mid]).to(device)
                def infer_fn(i,model=md,extractor=e):
                    inputs=extractor(i,return_tensors="pt").to(device)
                    with torch.no_grad():return model(**inputs)
                m[mid]={'model':infer_fn,'type':'logits'}
            else:m[mid]={'model':pipeline("image-classification",model=MODEL_PATHS[mid],device=device),'type':'pipeline'}
        except Exception as e:logger.error(f"Falha ao carregar {mid}: {e}")
    logger.info(f"✅ {len(m)} modelos de detecção base carregados!")
    return m

def load_sepael_models(path_m1, path_m2):
    try:
        model1 = xgb.XGBClassifier(); model1.load_model(path_m1)
        model2 = xgb.XGBClassifier(); model2.load_model(path_m2)
        logger.info("✅ Sistema SEPAEL (Modelos XGB 1 e 2) carregado com sucesso.")
        return model1, model2
    except Exception as e:
        logger.error(f"Erro ao carregar sistema SEPAEL: {e}"); return None, None

def get_decision(score_ai):
    if score_ai > 0.66:
        return "AI"
    elif score_ai < 0.34:
        return "REAL"
    else:
        return "Incerto"

def predict_with_sepael(image, detection_models, model1_xgb, model2_xgb, fft_extractor):
    base_scores = []; individual_results = []; aggregation_results = []
    ai_keywords = ['artificial','ai','fake','deepfake','ai_gen','aigenerated']
    real_keywords = ['real','human','realism','natural']
    
    for model_id in PIPELINE_CONFIG["use_models"]:
        model_info = detection_models[model_id]
        try:
            if model_info.get("type") == "custom_npr": scores = predict_npr_unified(image, model_info["model"])
            elif model_info.get('type') == 'pipeline':
                prediction = model_info['model'](image, top_k=5); scores = {p['label']: p['score'] for p in prediction}
            else:
                prediction = model_info['model'](image); logits = prediction.logits.cpu().numpy()[0]; probs = softmax(logits); scores = {CLASS_NAMES[model_id][j]: probs[j] for j in range(len(probs))}
            
            ai_score = 0.5; found_score = False
            for class_name, score in scores.items():
                if any(keyword in class_name.lower().replace('_', '') for keyword in ai_keywords):
                    ai_score = float(score); found_score = True; break
            if not found_score:
                for class_name, score in scores.items():
                    if any(keyword in class_name.lower().replace('_', '') for keyword in real_keywords):
                        ai_score = 1.0 - float(score); break
            
            base_scores.append(ai_score)
            real_score = 1 - ai_score
            razao = real_score / ai_score if ai_score > 1e-9 else float('inf')
            decision = get_decision(ai_score)
            individual_results.append([MODEL_PATHS[model_id].split('/')[-1], f"{ai_score:.4f}", f"{real_score:.4f}", f"{math.log10(razao):.2f}", decision])
        except Exception as e:
            logger.error(f"Erro na inferência do {model_id}: {e}"); base_scores.append(0.5)

    base_scores_np = np.array(base_scores).flatten()
    fft_features = fft_extractor.extract_ensemble_fft_features(image).reshape(1, -1)
    
    prob_model1_xgb_ai = model1_xgb.predict_proba(fft_features)[:, 0][0]
    real_score_m1_xgb = 1 - prob_model1_xgb_ai
    razao_m1_xgb = real_score_m1_xgb / prob_model1_xgb_ai if prob_model1_xgb_ai > 1e-9 else float('inf')
    decision_m1_xgb = get_decision(prob_model1_xgb_ai)
    individual_results.append(["model1_xgb (FFT)", f"{prob_model1_xgb_ai:.4f}", f"{real_score_m1_xgb:.4f}", f"{math.log10(razao_m1_xgb):.2f}", decision_m1_xgb])
    
    scores_for_agg = np.append(base_scores_np, prob_model1_xgb_ai)
    epsilon = 1e-9; scores_clipped = np.clip(scores_for_agg, epsilon, 1 - epsilon)
    logits = np.log(scores_clipped / (1 - scores_clipped))
    
    pesos = [0.47, 0.11, 0.10, 0.32]
    mean_logit_ponderado = np.average(logits, weights=pesos)
    log_odds_score_ai = 1 / (1 + np.exp(-mean_logit_ponderado))
    real_log_odds = 1 - log_odds_score_ai
    razao_log_odds = real_log_odds / log_odds_score_ai if log_odds_score_ai > 1e-9 else float('inf')
    decision_log_odds = get_decision(log_odds_score_ai)
    aggregation_results.append(["Media Log-odds ponderada", f"{log_odds_score_ai:.4f}", f"{real_log_odds:.4f}", f"{math.log10(razao_log_odds):.2f}", decision_log_odds])
    
    return individual_results, aggregation_results

# ==============================================================================
# SEÇÃO 4: LÓGICA DA INTERFACE GRADIO
# ==============================================================================
def run_analysis(image, generate_visuals):
    if image is None:
        return None, None, None, None, None, None, None, None, None, None
    try:
        individual_results, aggregation_results = predict_with_sepael(
            image, detection_models, model1_xgb, model2_xgb, fft_extractor
        )
        
        df_individual = pd.DataFrame(individual_results, columns=["Modelo", "Score AI", "Score Real", "Razão (Log)", "Classificação"])
        df_aggregation = pd.DataFrame(aggregation_results, columns=["Agregação", "Score AI", "Score Real", "Razão (Log)", "Classificação"])

        # FFT da imagem original é sempre calculada
        original_gray_np = np.array(image.convert('L')); original_fft_log_mag = fft_extractor._process_fft(original_gray_np)
        original_fft_img = Image.fromarray(cv2.equalizeHist((original_fft_log_mag * 255).astype(np.uint8)))

        if generate_visuals:
            (nlm_residue_img, median_residue_img, npr_residue_img, 
             nlm_fft_img, median_fft_img, npr_fft_img) = fft_extractor.generate_visualizations(image)
            ela_image = genELA(image)
            ela_gray_np = np.array(ela_image.convert('L')); ela_fft_log_mag = fft_extractor._process_fft(ela_gray_np)
            ela_fft_img = Image.fromarray(cv2.equalizeHist((ela_fft_log_mag * 255).astype(np.uint8)))
        else:
            # Se não for para gerar, retorna None para os outputs de imagem
            nlm_residue_img, median_residue_img, npr_residue_img, ela_image = None, None, None, None
            nlm_fft_img, median_fft_img, npr_fft_img, ela_fft_img = None, None, None, None
        
        return (df_individual, df_aggregation, original_fft_img,
                nlm_residue_img, median_residue_img, npr_residue_img, ela_image,
                nlm_fft_img, median_fft_img, npr_fft_img, ela_fft_img)

    except Exception as e:
        logger.error(f"Erro durante a análise: {e}", exc_info=True)
        return None, None, None, None, None, None, None, None, None, None

# ==============================================================================
# SEÇÃO 5: EXECUÇÃO DA APLICAÇÃO
# ==============================================================================

if __name__ == "__main__":
    detection_models = load_all_detection_models()
    model1_xgb, model2_xgb = load_sepael_models(MODEL1_XGB_FFT_PATH, MODEL2_XGB_AGG_PATH)
    fft_extractor = ResidueFFTFeatureExtractor(PIPELINE_CONFIG)

    if not all([detection_models, model1_xgb, model2_xgb]):
        logger.error("❌ ERRO CRÍTICO: Falha ao carregar um ou mais modelos. Verifique os logs e os caminhos dos arquivos.")
    else:
        logger.info("✅ Todos os sistemas carregados. Iniciando Gradio...")

        with gr.Blocks(theme=gr.themes.Soft(), css="#results_df {height: 150px; overflow: auto;} #agg_df {height: 100px; overflow: auto;}") as demo:
            gr.Markdown("# 🔍 SEPAEL: Análise Forense de Imagens")
            gr.Markdown("Faça o upload de uma imagem para análise pelos modelos especialistas e de agregação.")
            
            with gr.Row():
                with gr.Column(scale=1):
                    image_input = gr.Image(label="Imagem de Entrada", type='pil')
                with gr.Column(scale=1):
                    original_fft_output = gr.Image(label="FFT da Imagem de Entrada", type="pil")
                with gr.Column(scale=2):
                    # Tabela de resultados individuais
                    results_df = gr.Dataframe(
                        label="Resultados dos Modelos Individuais",
                        headers=["Modelo", "Score AI", "Score Real", "Razão(Log)", "Classificação"],
                        datatype=["str", "number", "number", "str", "str"],
                        elem_id="results_df"
                    )
                    
                    gr.Markdown("<br><br><br>") 
                    
                    # Tabela de agregação
                    aggregation_df = gr.Dataframe(
                        label="Agregação",
                        headers=["Agregação", "Score AI", "Score Real", "Razão(Log)", "Classificação"],
                        datatype=["str", "number", "number", "str", "str"],
                        elem_id="agg_df"
                    )

            with gr.Row():
                analyze_button = gr.Button("🚀 Analisar Imagem", variant="primary", scale=3)
                visuals_checkbox = gr.Checkbox(label="Gerar Visualizações Forenses (mais lento)", value=True, scale=1)
            
            with gr.Accordion("Análises Visuais Forenses (Opcional)", open=True):
                gr.Markdown("### Análise de Resíduos de Ruído")
                with gr.Row():
                    nlm_residue_output = gr.Image(label="Resíduo NLM", type="pil")
                    median_residue_output = gr.Image(label="Resíduo Mediana", type="pil")
                    npr_residue_output = gr.Image(label="Resíduo NPR", type="pil")
                    ela_output = gr.Image(label="Análise ELA", type="pil")
                
                gr.Markdown("### Análise no Domínio da Frequência (FFT dos Resíduos)")
                with gr.Row():
                    nlm_fft_output = gr.Image(label="FFT(log) Resíduo NLM", type="pil")
                    median_fft_output = gr.Image(label="FFT(log) Resíduo Mediana", type="pil")
                    npr_fft_output = gr.Image(label="FFT(log) Resíduo NPR", type="pil")
                    ela_fft_output = gr.Image(label="FFT(log) do ELA", type="pil")
            
            analyze_button.click(
                fn=run_analysis,
                inputs=[image_input, visuals_checkbox],
                outputs=[
                    results_df, aggregation_df, original_fft_output,
                    nlm_residue_output, median_residue_output, npr_residue_output, ela_output,
                    nlm_fft_output, median_fft_output, npr_fft_output, ela_fft_output
                ],
                api_name="analyze"
            )
        
        demo.queue(default_concurrency_limit=25).launch(server_name="10.61.242.183", server_port=7979, share=False, show_api=False)
