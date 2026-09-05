# Sobre
Este documento tem como objetivo mostrar como ajustar ``MANUALMENTE`` uma instalação padrão do Fedora para extrair o máximo de desempenho da placa AsRock BC-250.

Um dos objetivos aqui é municiar de conhecimento alguém que por conta dessa plaquinha maravilhosa, foi atraído pelo linux,  mas que não quer executar simplesmente um conjunto de scripts sem saber o que está acontecendo "sob o capô".

Um vídeo com a demonstração e explicação de cada um dos pontos deste documento pode ser assistido nesse link [Setup MANUAL do Linux CachyOS/Arch na BC-250](https://www.youtube.com/watch?v=wMqUmxJdXNo)

Capítulos do vídeo:

- [Premissas](https://youtu.be/wMqUmxJdXNo?si=e1XKdalXV8MXIv8e&t=398)

- [Recomendações básicas](https://youtu.be/wMqUmxJdXNo?si=14le6YOKBzC6raqX&t=516)

- [Instalando o yay ou o paru](https://youtu.be/wMqUmxJdXNo?si=y0CDuUUDy8yeEfvs&t=726)

- [Instalando os pré-requisito e dependências](https://youtu.be/wMqUmxJdXNo?si=ZstZabCPR_qHkd45&t=1130)

- [Instalando o ACPI Fix da BC-250](https://youtu.be/wMqUmxJdXNo?si=fr0NyevKKox8watC&t=1541)

- [Habilitando as 40 unidades computacionais (CUs)](https://youtu.be/wMqUmxJdXNo?si=FG6GdA2k9CpnKVec&t=2716)

- [Configurando a VRAM dinâmica](https://youtu.be/wMqUmxJdXNo?si=oYQXe3Kl5_4y_vV1&t=3213)

- [Configurando o overclock da GPU](https://youtu.be/wMqUmxJdXNo?si=RHcEwTcdupXLgu2c&t=3823)

- [Configurando o overclock da CPU](https://youtu.be/wMqUmxJdXNo?si=KFxx2_g2wZxQu4Y8&t=4327)

- [Convertendo ZRAM para ZSWAP](https://youtu.be/wMqUmxJdXNo?si=41uXkibmRpv-UIAO&t=4900)

# Importante

A comunidade em torno da BC-250 é extremamente unida e produtiva e alguns passos descritos aqui podem se tornar obsoletos muito rapidamente, portanto lembre-se sempre de consultar a página [AMD BC250 Documentation](https://elektricm.github.io/amd-bc250-docs/)

Procedimentos correntes em `04/09/2026`

# Premissas
- Sistema Operacional: **Fedora 44 com KDE/Plasma**
- Sitemas de arquivos: **BTRFS**
- Bootloader: **grub**
- Instalação limpa do Fedora 44 sem ter executado nenhum dos scripts automatizados
- Usuário com privilégio de sudo
- BIOS atualizada com a injeção do fix do ACPI 

## Conceitos básicos

- Ao copiar os comandos para execução, tente não copiar o bloco todo, copie linha a linha para ter controle sobre a execução e verificar se a mesma foi bem sucedida.

## Tópicos abordados
  
- [Primeiros passos pós instalação](#primeiros-passos-pós-instalação)  
- [Instalando as dependências e pré-requisitos](#instalando-as-dependências-e-pré-requisitos)  
- [Instalando as dependências e pré-requisitos](#instalando-as-dependências-e-pré-requisitos)  
- [Habilitandos as 40 unidades computacionais](#habilitando-as-40-unidades-computacionais)
- [Configurando a VRAM](#configurando-a-vram)
- [Overclock na GPU](#overclock-na-gpu)
- [Overclock na CPU](#overclock-na-cpu)
- [Convertendo a zram para zswap](#convertendo-a-zram-para-zswap)
- [Omitindo a mensagem RDSEED no boot](#omitindo-a-mensagem-rdseed-no-boot)
- Habilitando o Gaming Mode

## Primeiros passos pós instalação

### Atualizar o Fedora  
É recomendado sempre atualizar um sistema operacional logo após o primeiro boot, seja linux ou windows, obviamente que distribuições roling release que são instaladas a partir da internet não tem essa necessidade.  
  
No caso do fedora a atualização via linha de comando é feita com o seu gerenciador de pacotes que atualmente é o **DNF5**.  
O comando para atualizar é:
```
sudo dnf upgrade -y
```  
> [!TIP]  
> O parâmetro **"-y"** evita que o DNF solicite uma confirmação para prosseguir.  
  
### Habilitar os repositórios extras  
A filosofia do Fedora é não ter em seus repositórios "core" nenhum pacote que não seja open-source e de livre distribuição, por isso alguns pacotes base, como utilitários de multimída, não tem alguns codecs, mas isso não significa que não estejam disponíveis para o Fedora, para usá-los basta habilitar os repositórios **fusion free e nonfree**.  
  
Para habilitar esses repositórios basta executar os comandos a seguir:  
```
sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm -y && sudo dnf config-manager setopt fedora-cisco-openh264.enabled=1 -y
```
    
### Instalando os codecs de multimidia 
Após habilitarmos os repositórios free e nonfree vamos instalar/atualizar os codecs e utilitário de multimídia.
```
sudo dnf swap ffmpeg-free ffmpeg --allowerasing -y
```
```
sudo dnf install @multimedia --setopt="install_weak_deps=False" --exclude=PackageKit-gstreamer-plugin -y
```
```
sudo dnf install mesa-va-drivers-freeworld -y
```
```
sudo dnf swap mesa-vulkan-drivers{,-freeworld} -y
```  
  
## Instalando as dependências e pré-requisitos
Alguns dos próximos passos necessitam da instalação de pré-requisitos, são eles:

- **stress** - necessário para o procedimento de overclock/undervolt da CPU;
- **umr** - necessário para o script que libera as unidades computacionais (CUs) adicionais.
- **pipx** - será usado para configurar o overclock da CPU

Podemos fazer tudo em uma linha de comando única:
```
sudo dnf install stress umr pipx -y
```
  
## Habilitando as 40 unidades computacionais
Assumindo que o **umr** já está instalado (vide tópico [Instalando as dependências/pré-requisitos](#instalando-as-dependências)) o procedimento para liberar as unidades computacionais adicionais é relativamente simples.

**Baixando o script que libera as unidade computacionais adicionais**
```
mkdir ~/bc250 && cd ~/bc250 && curl -L -o bc250-cu-live-manager.sh https://raw.githubusercontent.com/WinnieLV/bc250-cu-live-manager/refs/heads/main/bc250-cu-live-manager.sh && chmod +x bc250-cu-live-manager.sh
```
**Executando o script**
```
sudo ~/bc250/bc250-cu-live-manager.sh
```
Uma vez o script estando em execução a sequência mais comum de procedimentos é: 

- tecla "f" para habilitar os 40 CUs;

- tecla "i" para instalar o serviço;

- tecla "w" para escrever a tabela com os CUs adicionais habilitados;

- tecla "q" para encerrar o script.

Obs.: A versão do script de **30/07/2026** tem uma opção para habilitar os dois cores adicionais desabilitados de fábrica.

**Referência:**

[WinnieLV/bc250-cu-live-manager#cpu-core-unlock](https://github.com/WinnieLV/bc250-cu-live-manager#cpu-core-unlock)

## Configurando a VRAM
Recentemente a atualização da BIOS para configurar a alocação dinâmica da VRAM deixou de ser necessária e isso pode ser conseguido com uma aplicação.
  
> [!IMPORTANT]  
> Só execute os comandos desse tópico se a configuração da BIOS estiver igual aos parâmetros de fábrica.

Pessoalmente eu tenho conseguido bons resultados com a alocação imediata de 6GB e a possibilidade de alocar mais 5GB, totalizando 11GB de VRAM máxima. Alguns jogos não lidam bem com a configuração dinâmica iniciando em 512MB, além de que quando você começa com a VRAM em 512MB ela "gasta" um tempinho requisitando da RAM e liberando a VRAM depois que ela não é mais necessária. No meu caso, os 6GB são um ponto de equilíbrio bom.

Esse resultado pode ser obtido com a aplicação **bc250memcfg** e um parâmetro do kernel adicional no boot.

Para alcançarmos essa combinação devemos seguir os seguintes passos:

**Baixando a aplicação e descompactando na pasta ~/bc250**
```
cd ~/bc250 && wget https://github.com/fanoush/bc250_memcfg/releases/download/v0.1/bc250_memcfg.zip && unzip bc250_memcfg.zip && cd ~/bc250/bc250_memcfg
```

**Configurando o UMA_SIZE para 6144MB (6GB)**
```
sudo ./bc250memcfg UMA_SIZE 6144
```

**Configurando o parâmetro do kernel para alocar mais 5GB de VRAM se for necessário**

O parâmetro em questão é o **ttm.pages_limit**.

Para calcular o valor a ser passado para o **ttm.pages_limit** fazemos a seguinte conta:
```
Valor dinâmico possível x, no caso 5G
((x * 1024) * 1024) / 4 
((5 * 1024) * 1024) / 4 = 1310720
```
Após obter o valor a ser passado vamos configurar o grub para adicionar esse parâmetro de inicialização ao kernel.  
```
sudo grubby --args=tm.pages_limit=1310720 --update-kernel=ALL
```
  
Reinicie o Fedora e sua VRAM estará configurada para 6GB e podendo chegar a 11GB.

**Referências:**

[AMD BC250 Documentation/VRAM Configuration Guide](https://elektricm.github.io/amd-bc250-docs/bios/vram/)

[fanoush/bc250_memcfg](https://github.com/fanoush/bc250_memcfg)


## Overclock na GPU
Por padrão a GPU da BC-250 opera em 1500 MHz constantes e isso não é eficiente em consumo, além de limitar o potencial dessa plaquinha tão maravilhosa.

Essa operação padrão pode ser subvertida com a instalação do **Cyan Skillfish GPU Governor** habilitando frequências de 350 MHz até 2230 MHz e é esse o próximo passo da nossa jornada.

`Obs.: Frequências de 350 MHz só são possíveis com um kernel com patch aplicado e isso já é padrão no CachyOS e no Arch Linux`

**Primeiro passo é instalação do serviço**
```
sudo dnf copr enable filippor/bazzite -y
```
```
sudo dnf install cyan-skillfish-governor-smu -y
```
Durante a instalação o serviço criará um arquivo de configuração **(config.toml)** na pasta **/etc/cyan-skillfish-governor-smu**

Esse arquivo virá configurado com parâmetros seguros de operação variando a frequência de **1000 MHz** a **1850 Mhz**.

Para testar a estabilidade a sugestão é iniciar o serviço sem habilitá-lo, ou seja, se ocorrer alguma instabilidade, com um simples reboot a placa voltará para a operação padrão a 1500 MHz.

**Iniciando o serviço e verificando a estabilidade**
```
sudo systemctl start cyan-skillfish-governor-smu
```
Após iniciar o serviço é recomendado executar algum benchmark da GPU para verificar a estabilidade. Sugestão, testar com o [Unigine Superposition](https://benchmark.unigine.com/superposition)

Confirmada a estabilidade, pode-se habilitar o serviço para iniciar com o boot do sistema.

**Habilitando o GPU Governor para iniciar com o boot**
```
sudo systemctl enable cyan-skillfish-governor-smu
```

Com o tempo pode-se brincar com as frequências e voltagens, para isso recomendo a leitura da documentação do desenvolvedor.

**Referência:**

[filippor/cyan-skillfish-governor](https://github.com/filippor/cyan-skillfish-governor)

## Overclock na CPU

A faixa de frequência padrão de operação da CPU depois de aplicado o fix do ACPI é de 800 MHz a 3500 MHz, mas é possível levá-la até 4000 MHz e fazer um undervolt o que resulta em um menor aquecimento quando em altas cargas.

Para habilitar o overclock/unvervolt via SMU existe uma ferramenta chamada **bc250_smu_oc**

A seguir temos os passos para configurar essas possibilidades.

**Fazendo o download e ativando o bc250_smu_oc**
```
cd ~/bc250 && git clone https://github.com/bc250-collective/bc250_smu_oc.git && cd ~/bc250/bc250_smu_oc && pipx install . && chmod +x *.py
```
O comando acima faz o download da ferramenta com o comando **"git clone"**, vai para o diretório da mesma e ativa um ambiente python para rodar uma aplicão em modo isolado via **"pipx"**, após isso finaliza configurando o atributo de execução nos scripts python com o comando **"chmod"** e o parâmetro **"+x"**. Lembrar do encadeamento de comandos usando o **"&&"**

**Testando a capacidade de overclock e undervolt da CPU**
```
sudo ./bc250_detect.py -f 3850 -v 1119 -t 89
```
Esse comando irá testar a frequência de 3850 MHz com 1119 mV, se tudo der certo ele vai concluir o teste com sucesso.

Se o script der erro você pode tentar variar a frequência e a voltagem (variando aos poucos).

O script terminando com sucesso ele gera um arquivo na mesma pasta chamado **overclock.conf** e está na hora de fixar esse parâmetros.

**Tornando os resultados dos testes acima permanente**
```
sudo ./bc250_apply.py --install overclock.conf && sudo systemctl enable --now bc250-smu-oc
```
A dupla de comandos acima instalam e habilitam o serviço **bc250-smu-oc**.

Obs.: Existe um parâmetro para o **bc250_detect.py** que é o **"--keep"** que após o script terminar os parâmetros do teste permanecem aplicados até o reboot.

**Referência:**

[bc250-collective/bc250_smu_oc](https://github.com/bc250-collective/bc250_smu_oc)

## Convertendo a zram para zswap
O Fedora, como muitos sistemas modernos, usa o swap em RAM, mas em um sistema com somente 16GB que ainda é compartilhado com a GPU, isso tem um custo muito alto e pode gerar problemas, por isso a recomendação é converter a **ZRAM** em **ZSWAP**

Os passos a seguir devem ser executados com cuidado.
```
sudo dnf remove zram-generator-defaults
```
```
echo -e "add_drivers+=\" lz4 lz4_compress \"" | sudo tee -a /etc/dracut.conf.d/zswap.conf
```
```
sudo grubby --args="systemd.zram=0 zswap.enabled=1 zswap.shrinker_enabled=1 zswap.compressor=lz4 zswap.max_pool_percent=30"
```

**Execute a seguinte sequência de comandos UM POR UM, só passando ao próximo se o anterior executar sem erros**
```
sudo btrfs subvolume create /swap
```
```
sudo btrfs filesystem mkswapfile --size 8g --uuid clear /swap/swapfile
```
```
sudo swapon /swap/swapfile
```
```
echo "/swap/swapfile none swap defaults 0 0" | sudo tee -a /etc/fstab
```
  
Reinicie o Fedora e a troca para ZSWAP estará concluída

## Omitindo a mensagem RDSEED no boot
Os processadores baseados na APU Cyan Skillfish (Zen 2) não são compatíveis com a instrução RDSEED e no boot do linux aparece uma mensagem informando que isso está sendo desabilitado. Não há qualquer problema nessa mensagem e isso não tem maiores efeitos além dos estéticos.

Apesar de atualmente não gerar qualquer problema, além do incômodo estético, é possível omitir essa mensagem no boot, bastando para isso adicionar mais um parâmetro ao kernel.

Aproveitando o momento de editar os parâmetros de boot para incluir o mitigations=off que melhora o desempenho em algumas situações relacionadas a jogos

**Novamente vamos editar as opções de boot do limine**
```
sudo nano /etc/default/limine
```
Localizar a linha **"KERNEL_CMDLINE[default]"** e adicionar depois de **quiet** os parâmetros
```
loglevel=0 mitigations=off
```
O resultado ficará algo parecido com a linha a seguir:

**KERNEL_CMDLINE[default]+="quiet loglevel=0 mitigations=off nowatchdog splash...**

Use a combinação de teclas **ctrl + s** para salvar o arquivo e **ctrl + x** para encerrar o editor nano

**Após isso atualizar o bootloader com o comando:**
```
sudo limine-update
```



## Conclusão
A maior parte desses procedimentos é válida para o Arch Linux, bastando as premissas do Limine e do BTRFS estarem atendidas.
