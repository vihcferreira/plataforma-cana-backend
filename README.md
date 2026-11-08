# Plataforma Cana

Repositório responsável pelo desenvolvimento da **Plataforma Cana**.

## 🌿 Fluxo de Branches

O projeto utiliza três branches principais:

* `develop` — desenvolvimento e integração das funcionalidades.
* `homolog` — ambiente de homologação e validação.
* `prod` — versão estável em produção.

### Fluxo

```text
feature/* / bugfix/*
        ↓
     develop
        ↓
     homolog
        ↓
      prod
```

> Não realizar commits diretamente nas branches `develop`, `homolog` ou `prod`.

---

## 🌱 Criação de Branches

As branches de desenvolvimento devem ser criadas a partir da `develop`.

### Nova funcionalidade

```bash
git checkout develop
git pull origin develop
git checkout -b feature/nome-da-funcionalidade
```

Exemplo:

```bash
git checkout -b feature/cadastro-produtor
```

### Correção de bug

```bash
git checkout develop
git pull origin develop
git checkout -b bugfix/corrigir-validacao
```

### Correção urgente em produção

Para correções que precisam ser realizadas diretamente para uma versão de produção:

```bash
git checkout prod
git pull origin prod
git checkout -b hotfix/corrigir-erro-producao
```

---

## 📝 Padrão de Commits

O projeto utiliza **Conventional Commits**.

Formato:

```text
tipo: descrição
```

Tipos permitidos:

| Tipo       | Utilização                  |
| ---------- | --------------------------- |
| `feat`     | Nova funcionalidade         |
| `fix`      | Correção de bug             |
| `refactor` | Refatoração de código       |
| `docs`     | Documentação                |
| `test`     | Testes                      |
| `chore`    | Manutenção/configuração     |
| `style`    | Formatação/estilo           |
| `perf`     | Melhoria de desempenho      |
| `build`    | Build/dependências          |
| `ci`       | Integração/entrega contínua |

### Exemplos

```bash
git commit -m "feat: adiciona cadastro de produtores"
```

```bash
git commit -m "fix: corrige validação do CPF"
```

```bash
git commit -m "refactor: reorganiza serviço de autenticação"
```

```bash
git commit -m "docs: atualiza documentação da API"
```

```bash
git commit -m "test: adiciona testes do cadastro de produtores"
```

### Boas práticas

* Escrever commits objetivos e descritivos.
* Utilizar o verbo no presente.
* Evitar commits genéricos como `update`, `alterações` ou `mudanças`.
* Cada commit deve representar uma alteração lógica.
* Evitar misturar funcionalidades diferentes no mesmo commit.

---

## 🔀 Pull Requests

Toda alteração deve passar por Pull Request.

Fluxo padrão:

```text
feature/* / bugfix/*
        ↓
     Pull Request
        ↓
     develop
```

Após validação:

```text
develop
   ↓
homolog
```

Após aprovação em homologação:

```text
homolog
   ↓
prod
```

Pull Requests devem:

* Possuir título descritivo.
* Explicar o que foi alterado.
* Informar possíveis impactos.
* Ser revisados antes do merge.
* Não conter código desnecessário ou arquivos temporários.

---

## 🚫 Regras das Branches Principais

As branches abaixo devem ser protegidas:

```text
develop
homolog
prod
```

Recomenda-se bloquear:

* Push direto.
* Force push.
* Exclusão da branch.
* Merge sem Pull Request.
* Merge sem revisão, quando aplicável.

A branch `prod` deve conter somente código aprovado e pronto para produção.

---

## 📌 Exemplo de fluxo completo

```bash
# Atualizar develop
git checkout develop
git pull origin develop

# Criar branch
git checkout -b feature/cadastro-produtor

# Desenvolver...

# Commit
git add .
git commit -m "feat: adiciona cadastro de produtores"

# Enviar branch
git push -u origin feature/cadastro-produtor
```

Depois:

```text
feature/cadastro-produtor
            ↓
         develop
            ↓
         homolog
            ↓
          prod
```

---

## 🔐 Boas práticas

* Nunca versionar senhas, tokens ou chaves de API.
* Utilizar `.env` para configurações sensíveis.
* Manter um `.env.example` no repositório.
* Não versionar arquivos temporários ou dependências que possam ser instaladas pelo gerenciador do projeto.
* Manter o README atualizado.
* Antes de iniciar uma tarefa, atualizar a branch `develop`.
* Sempre revisar as alterações antes de criar o Pull Request.

---

## 🐳 Ambiente de Banco de Dados Local (Docker)

Para subir o banco de dados MySQL localmente com as tabelas pré-configuradas, utilizamos o Docker com Docker Compose.

### Estrutura necessária

Certifique-se de que a estrutura de arquivos no projeto esteja da seguinte forma:

```text
plataforma-cana-backend/
├── docker-compose.yml
├── init/
│   └── init.sql
└── ...
```

> **Nota:** Os arquivos `docker-compose.yml` e `init/init.sql` não devem ser versionados com senhas reais (consulte o `.gitignore`).

### 1. Criar o arquivo `docker-compose.yml`

Na raiz do projeto (mesmo nível da pasta `init/`), crie o arquivo `docker-compose.yml`:

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    container_name: mysql_water_db
    restart: always
    environment:
      MYSQL_ROOT_PASSWORD: rootpassword
      MYSQL_DATABASE: water_management
      MYSQL_USER: user
      MYSQL_PASSWORD: password
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
      - ./init:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      timeout: 20s
      retries: 10

volumes:
  mysql_data:
```

### 2. Criar o script de inicialização `init/init.sql`

Crie o diretório `init/` e dentro dele o arquivo `init.sql` contendo o script DDL de criação das tabelas e do banco de dados. Os scripts colocados nesta pasta são executados automaticamente no primeiro boot do container.

### 3. Comandos de execução

* **Iniciar o container em segundo plano:**
  ```bash
  docker compose up -d
  ```

* **Visualizar logs do banco:**
  ```bash
  docker compose logs -f mysql
  ```

* **Parar o container:**
  ```bash
  docker compose down
  ```

* **Parar e remover volumes (reinicializar o banco do zero):**
  ```bash
  docker compose down -v
  ```

### Dados de Conexão

| Campo | Valor |
| --- | --- |
| **Host** | `localhost` |
| **Porta** | `3306` |
| **Database** | `water_management` |
| **Usuário** | `user` |
| **Senha** | `password` |
| **Root Password** | `rootpassword` |

---

## 🚀 Inicialização do Servidor Backend (FastAPI)

Após subir o container do MySQL, siga as etapas abaixo para configurar o ambiente e executar a API.

### 1. Criar e Ativar o Ambiente Virtual (venv)

* **No Windows (PowerShell):**
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```

* **No Linux / macOS:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### 2. Instalar as Dependências

Com o ambiente virtual ativado:
```bash
pip install -r requirements.txt
```

### 3. Iniciar o Servidor

Execute o Uvicorn com recarregamento automático (`--reload`):
```bash
uvicorn main:app --reload --port 8000
```

O servidor estará disponível em:
* **API Base:** [http://localhost:8000](http://localhost:8000)
* **Documentação Swagger (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Documentação Alternativa (ReDoc):** [http://localhost:8000/redoc](http://localhost:8000/redoc)
---

## 📊 Parâmetros de Medição e Classificação de Risco

O backend utiliza critérios analíticos bem definidos para telemetria contínua dos pontos de monitoramento (`Map_Point`), avaliação do ciclo hídrico (`Measurement`) e fiscalização automática de descartes.

### 1. Faixas Operacionais dos Pontos de Monitoramento (`Map_Point`)

No serviço de telemetria autônoma (`telemetry_service.py`), cada medição é classificada conforme os seguintes intervalos operacionais:

| Parâmetro | Faixa Normal (Baixo Risco) | Faixa de Atenção (Alerta / `warn`) | Faixa Crítica (`crit`) | Alvo Médio |
| :--- | :--- | :--- | :--- | :--- |
| **pH** | `6.2` a `8.4` | `5.5 <= pH < 6.2` ou `8.4 < pH <= 9.2` | `< 5.5` ou `> 9.2` | `~7.2` |
| **Turbidez** | `<= 30 NTU` | `> 30` a `<= 60 NTU` | `> 60 NTU` | `~22 NTU` |
| **Volume de Efluentes** | `<= 3.800 m³` | `> 3.800` a `<= 4.800 m³` | `> 4.800 m³` | `~2.800 m³` |
| **Contaminantes** | `<= 1.2 mg/L` | `> 1.2` a `<= 3.2 mg/L` | `> 3.2 mg/L` | `~0.6 mg/L` |

### 2. Lógica de Atribuição do Nível de Risco (`risk_map_point`)

A telemetria avalia simultaneamente o número de violações críticas (`crit_count`) e violações em atenção (`warn_count`):

* **`critical` (Crítico):** `crit_count >= 2`
  * Ocorre quando 2 ou mais parâmetros entram na faixa crítica simultaneamente.
  * **Ação Automática:** Gera automaticamente registros no banco de dados vinculados ao mesmo `tenant_id`:
    1. Uma nova **Ocorrência** (`Occurrence`) com risco crítico e status de análise.
    2. Um novo **Alerta** (`Alert`) de severidade crítica com recomendação operacional imediata.
    3. Um registro no **Histórico de Eventos** (`History_Event`) com severidade crítica.
* **`medium` (Médio):** `crit_count == 1` ou `warn_count >= 2`
  * Ocorre quando há 1 parâmetro crítico isolado ou 2 ou mais parâmetros na faixa de atenção preventiva.
* **`low` (Baixo):** `crit_count == 0` e `warn_count <= 1`
  * Todos os parâmetros operando em conformidade ou com apenas uma oscilação leve.

### 3. Laudos Físico-Químicos Laboratoriais (`Measurement` / CONAMA 430)

No módulo do **Ciclo Hídrico** (`routers/ciclo_hidrico.py`), os laudos laboratoriais de admissão, estocagem e fertirrigação são avaliados por meio da função `avaliar_qualidade_medicao`:

* **Limites CONAMA 430 / Agroindustrial:**
  * **pH:** entre `6.0` e `9.0`
  * **Oxigênio Dissolvido (OD):** `>= 4.0 mg/L`
  * **Turbidez:** `<= 40.0 NTU`
  * **DBO (Demanda Bioquímica de Oxigênio):** `<= 60.0 mg/L`
  * **DQO (Demanda Química de Oxigênio):** `<= 150.0 mg/L`
* **Classificação por Machine Learning (`modelo_qualidade_agua.pkl`):**
  * As variáveis `[pH, Temperatura_C, DBO_mgL, Turbidez_NTU]` são submetidas ao modelo supervisionado scikit-learn.
  * O status resulta em **"Própria"** se aprovado tanto pelas normas CONAMA quanto pelo modelo de IA, ou **"Poluída (Risco de Efluentes)"** caso haja inconformidade.
  * Descartes realizados em áreas não homologadas (`Area_Of_Disposal.is_validated_for_disposal = False`) ou com laudo poluído acionam automaticamente fiscalização via `Alert`, `Occurrence` e `History_Event`.
