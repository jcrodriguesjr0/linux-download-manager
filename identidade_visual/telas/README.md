# Nova Identidade Visual — Mockups e Telas da Nova Interface (LDM)

Esta pasta contém os mockups conceituais e guias visuais que demonstram como a interface do **Linux Download Manager (LDM)** é modernizada de um clone IDM 2005 para um aplicativo nativo Linux moderno.

---

## 🚀 Principais Mudanças em Relação à Interface Antiga

| Elemento | Interface Anterior (Clone IDM) | Nova Interface LDM |
|---|---|---|
| **Barra Superior** | Barra de ferramentas antiquada com 14 botões pequenos lado a lado | **HeaderBar moderna do GTK/GNOME** com os 3 botões essenciais (`+ URL`, `★ Vídeo`, `Pausar Tudo`) e o restante no menu |
| **Linha de Download** | Barra de progresso azul genérica e estática | **"Linha de Download Viva"**: mini-mapa com segmentos em Crimson Red mostrando os threads de conexão baixando ativamente em tempo real |
| **Destaque de Vídeo** | Ícones misturados na mesma cor | **Cor Âmbar (`#F59E0B`) exclusiva** para detecção e captura de streams de vídeo |
| **Velocidade & Métricas** | Números em fonte proporcional que "dançam" na tela ao mudar | **JetBrains Mono tabular (`tabular-nums`)** para velocidades, tamanhos e tempo restante |
| **Gráfico de Rede** | Oculto em janelas secundárias | **Sparkline de velocidade em tempo real** integrado com elegância no rodapé |
| **Steam Deck / Touch** | Botões pequenos de desktop difíceis de tocar | **Alvos de toque mínimos de 44 px** para controle confortável via touchscreen ou touchpad |

---

## 📁 Arquivos Disponíveis nesta Pasta
- **[`main.png`](main.png)** / `mockup_janela_principal.svg`: Mockup em alta resolução da janela principal do LDM.
- **[`progress.png`](progress.png)** / `mockup_progresso.svg`: Diálogo de progresso detalhado com o mapa de 16 conexões ativas.

