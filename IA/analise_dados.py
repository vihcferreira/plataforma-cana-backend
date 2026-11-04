import pandas as pd

# 1. CARREGANDO OS DADOS
print("--- INICIANDO ANÁLISE DE DADOS ---")
df = pd.read_csv('dataset_agua_agroindustria.csv')
print(f"Dataset carregado com {df.shape[0]} linhas e {df.shape[1]} colunas.\n")

# 2. IDENTIFICANDO VALORES AUSENTES (Exigência do Tópico 9)
print("--- VERIFICANDO DADOS AUSENTES/NULOS ---")
nulos = df.isnull().sum()
print(nulos)
print("\nNota: Lembra que plantamos 50 valores nulos no pH de propósito? Eles estão aí!\n")

# 3. LIMPEZA E TRATAMENTO (Exigência do Tópico 9)
print("--- REALIZANDO LIMPEZA DE DADOS ---")
# Como o pH não pode ficar vazio para a IA, vamos preencher os nulos com a MEDIANA do pH
mediana_ph = df['pH'].median()
df['pH'] = df['pH'].fillna(mediana_ph)

# Verificando se limpou tudo
nulos_apos_limpeza = df['pH'].isnull().sum()
print(f"Valores nulos no pH após limpeza: {nulos_apos_limpeza}\n")

# 4. ANÁLISE EXPLORATÓRIA BÁSICA (Exigência do Tópico 9)
print("--- ANÁLISE EXPLORATÓRIA (ESTATÍSTICAS) ---")
# O método describe() tira média, desvio padrão, mínimo e máximo de tudo
estatisticas = df.describe().round(2)
print(estatisticas[['pH', 'DBO_mgL', 'Turbidez_NTU']])
print("\n")

print("--- DISTRIBUIÇÃO DA QUALIDADE DA ÁGUA ---")
# Verificando quantas águas estão boas (1) e quantas estão poluídas (0)
contagem = df['Qualidade_Agua'].value_counts()
print(f"Água Própria (1): {contagem.get(1, 0)} amostras")
print(f"Água Poluída (0): {contagem.get(0, 0)} amostras")

# 5. SALVANDO OS DADOS LIMPOS PARA O MODELO DE IA
df.to_csv('dataset_limpo.csv', index=False)
print("\nDados limpos salvos em 'dataset_limpo.csv'. Prontos para a IA!")