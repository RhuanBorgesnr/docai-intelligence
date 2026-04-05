# Guia de Contribuição

Obrigado por considerar contribuir com o **DocAI Intelligence**! Este documento fornece diretrizes para contribuir com o projeto.

## Código de Conduta

Ao participar deste projeto, você concorda em manter um ambiente respeitoso e colaborativo.

## Como Contribuir

### Reportando Bugs

1. Verifique se o bug já não foi reportado nas [Issues](https://github.com/seu-usuario/docai-intelligence/issues)
2. Se não encontrar, crie uma nova issue com:
   - Título claro e descritivo
   - Passos para reproduzir o problema
   - Comportamento esperado vs. comportamento atual
   - Screenshots se aplicável
   - Ambiente (SO, versão do Python, etc.)

### Sugerindo Melhorias

1. Crie uma issue com a tag `enhancement`
2. Descreva a funcionalidade desejada
3. Explique por que seria útil para o projeto

### Pull Requests

1. **Fork** o repositório
2. **Clone** seu fork:
   ```bash
   git clone https://github.com/seu-usuario/docai-intelligence.git
   ```
3. **Crie uma branch** para sua feature:
   ```bash
   git checkout -b feature/minha-feature
   ```
4. **Faça suas alterações** seguindo os padrões do projeto
5. **Commit** suas mudanças:
   ```bash
   git commit -m "feat: adiciona nova funcionalidade X"
   ```
6. **Push** para seu fork:
   ```bash
   git push origin feature/minha-feature
   ```
7. Abra um **Pull Request**

## Padrões de Código

### Python (Backend)

- Siga o [PEP 8](https://pep8.org/)
- Use type hints quando possível
- Docstrings em português ou inglês
- Máximo de 100 caracteres por linha

```python
def extract_indicators(text: str, max_chars: int = 4000) -> dict:
    """
    Extrai indicadores financeiros do texto.

    Args:
        text: Texto do documento
        max_chars: Máximo de caracteres a processar

    Returns:
        Dicionário com indicadores extraídos
    """
    pass
```

### JavaScript/React (Frontend)

- Use ESLint e Prettier
- Componentes funcionais com hooks
- Nomes de componentes em PascalCase
- Nomes de funções em camelCase

```javascript
const DocumentCard = ({ document, onDelete }) => {
  const handleDelete = () => {
    onDelete(document.id);
  };

  return (
    <div className="card">
      <h3>{document.title}</h3>
      <button onClick={handleDelete}>Excluir</button>
    </div>
  );
};
```

### Commits

Seguimos o padrão [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` nova funcionalidade
- `fix:` correção de bug
- `docs:` alterações em documentação
- `style:` formatação, sem alteração de código
- `refactor:` refatoração de código
- `test:` adição ou correção de testes
- `chore:` tarefas de manutenção

Exemplos:
```
feat: adiciona extração de EBITDA
fix: corrige cálculo de margem líquida
docs: atualiza README com instruções de instalação
```

## Estrutura do Projeto

```
src/
├── accounts/        # Autenticação e usuários
├── ai/              # Módulos de IA
├── companies/       # Multi-tenancy
├── core/            # Configurações Django
├── documents/       # Gestão de documentos
└── search/          # Busca semântica

frontend/
├── src/
│   ├── components/  # Componentes reutilizáveis
│   ├── pages/       # Páginas
│   └── services/    # Chamadas à API
```

## Setup de Desenvolvimento

### Backend

```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# Instalar dependências de desenvolvimento
pip install pytest pytest-django black flake8 isort

# Rodar linting
black src/
flake8 src/
isort src/
```

### Frontend

```bash
cd frontend
npm install
npm run lint
npm run format
```

## Testes

### Backend

```bash
cd src
python manage.py test

# Com cobertura
coverage run manage.py test
coverage report -m
```

### Frontend

```bash
cd frontend
npm test
```

## Revisão de Código

Todos os PRs passam por revisão. Checklist:

- [ ] Código segue os padrões do projeto
- [ ] Testes foram adicionados/atualizados
- [ ] Documentação foi atualizada
- [ ] Não há vulnerabilidades de segurança
- [ ] Build passa sem erros

## Dúvidas

Se tiver dúvidas, abra uma issue com a tag `question` ou entre em contato com os mantenedores.

---

**Obrigado por contribuir!** 🎉
