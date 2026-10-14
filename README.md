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

