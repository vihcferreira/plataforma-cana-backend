import pandas as pd
import numpy as np

# Configurando a semente para resultados consistentes
np.random.seed(42)

# Gerando 1000 amostras de coleta de água
n_amostras = 1000

# Simulando características da água afetas por efluentes (Vinhaça)
# Vinhaça geralmente abaixa o pH, aumenta DBO e Turbidez
ph = np.random.normal(loc=6.5, scale=1.5, size=n_amostras)
temperatura = np.random.normal(loc=25.0, scale=4.0, size=n_amostras)
dbo = np.random.exponential(scale=50.0, size=n_amostras) # Demanda Biológica de Oxigênio
turbidez = np.abs(np.random.normal(loc=30.0, scale=15.0, size=n_amostras))

# Criando a regra para a "Qualidade da Água" (A variável que a IA vai prever)
# 1 = Própria, 0 = Poluída (por efluentes)
qualidade = []
for i in range(n_amostras):
    # Regra lógica simulando poluição severa
    if ph[i] < 5.0 or ph[i] > 8.5 or dbo[i] > 60.0 or turbidez[i] > 40.0:
        qualidade.append(0) # Poluída
    else:
        qualidade.append(1) # Própria

# Montando a tabela de dados (DataFrame)
dados = pd.DataFrame({
    'pH': np.round(ph, 2),
    'Temperatura_C': np.round(temperatura, 1),
    'DBO_mgL': np.round(dbo, 2),
    'Turbidez_NTU': np.round(turbidez, 2),
    'Qualidade_Agua': qualidade
})

# TRUQUE DE MESTRE: Adicionando 50 valores nulos de propósito 
# para você ter o que "limpar" na etapa do Tópico 9
indices_nulos = np.random.choice(dados.index, size=50, replace=False)
dados.loc[indices_nulos, 'pH'] = np.nan

# Salvando em um arquivo CSV
nome_arquivo = 'dataset_agua_agroindustria.csv'
dados.to_csv(nome_arquivo, index=False)
print(f"Dataset '{nome_arquivo}' gerado com sucesso com {n_amostras} registros!")