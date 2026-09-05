# bc250-gfxclk-fix

Corrige a exibição da frequência da GPU na placa AMD BC-250 (Cyan Skillfish gfx1013) quando todos os 8 núcleos físicos de CPU estão ativados.

Trata-se de uma correção pequena, independente e restrita ao espaço do usuário. Ela não exige um módulo de kernel, uma recompilação do kernel ou gravações com privilégio de root em qualquer local abaixo de /usr. Ela corrige apenas a exibição do clock da GPU -- nada mais.

## Instalação

```bash
sudo ./install.sh
```
