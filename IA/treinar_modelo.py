import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
import joblib
print("--- INICIANDO O MECANISMO PREDITIVO ---")

# 1. Carregando os dados limpos
df = pd.read_csv('dataset_limpo.csv')

# 2. Separando as Variáveis (X) do Alvo a ser previsto (y)
X = df[['pH', 'Temperatura_C', 'DBO_mgL', 'Turbidez_NTU']]
y = df['Qualidade_Agua']

# 3. Separando em Treinamento e Teste (Exigência do Tópico 9)
# 80% dos dados para a IA aprender, 20% para fazermos a prova final
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
print(f"Dados separados: {len(X_train)} para treino e {len(X_test)} para teste.\n")

# 4. Treinando o Modelo (Algoritmo de Árvores de Decisão)
print("Treinando a Inteligência Artificial...")
modelo = RandomForestClassifier(n_estimators=100, random_state=42)
modelo.fit(X_train, y_train)
print("Treinamento concluído com sucesso!\n")

# 5. Avaliando a Inteligência Artificial
print("--- RESULTADOS DA AVALIAÇÃO ---")
previsoes = modelo.predict(X_test)
acuracia = accuracy_score(y_test, previsoes)

print(f"Acurácia (Acertos): {acuracia * 100:.2f}%\n")
print("Relatório Detalhado:")
print(classification_report(y_test, previsoes, target_names=['Poluída (0)', 'Própria (1)']))

# 6. Teste Prático (Simulando uma nova coleta de água no rio)
print("\n--- TESTE PRÁTICO COM ÁGUA DESCONHECIDA ---")
nova_amostra = pd.DataFrame({'pH': [4.2], 'Temperatura_C': [28.5], 'DBO_mgL': [70.0], 'Turbidez_NTU': [45.0]})
previsao_nova = modelo.predict(nova_amostra)
status = "Própria" if previsao_nova[0] == 1 else "Poluída (Risco de Efluentes)"
print(f"Resultado da previsão para a nova amostra: {status}")

# ==========================================
# 7. EXPORTANDO O MODELO PARA O BACKEND
# ==========================================
joblib.dump(modelo, 'modelo_qualidade_agua.pkl')
print("\n✅ Modelo salvo com sucesso como 'modelo_qualidade_agua.pkl'!")