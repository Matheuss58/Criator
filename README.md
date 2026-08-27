# Criator

Editor local de vídeos Phonk. O Criator seleciona o melhor trecho musical,
analisa as cenas, cria uma timeline narrativa sincronizada e renderiza em 60
FPS usando a GPU NVIDIA quando disponível.

## Requisitos

- Windows 10/11
- Python 3.11 ou 3.12
- Node.js LTS
- FFmpeg e FFprobe no PATH
- GPU NVIDIA recomendada; CPU funciona como fallback

## Instalação

Abra o PowerShell nesta pasta:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\instalar.ps1
```

## Uso

```powershell
.\start.ps1
```

Abra `http://localhost:8080`. Escolha o vídeo, a música, o formato vertical ou
horizontal e a duração exata. O backend fica somente em `localhost:5001`.

## Como o motor trabalha

1. Encontra uma janela musical forte e mapeia beats/energia.
2. Detecta, divide e pontua tomadas por movimento, nitidez, exposição e rosto.
3. Planeja hook, apresentação, buildup, drop, release e loop.
4. Aplica cortes, speed ramps, punch-ins e acabamento com cooldown visual.
5. Renderiza em blocos e valida resolução, 60 FPS e duração.

Cada resultado também produz `final.timeline.json` na pasta temporária do job,
útil para diagnóstico. Arquivos enviados e resultados são removidos após o
download ou expiração.

## Desempenho

O motor analisa proxies pequenos e renderiza com `h264_nvenc` quando disponível.
Não usa serviços de nuvem, API ou modelo generativo obrigatório.
