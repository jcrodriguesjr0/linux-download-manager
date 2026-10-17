# Nova Identidade Visual — Conjunto de Ícones do Sistema (LDM)

Esta pasta contém o **conjunto próprio e unificado de 21 ícones vetoriais de linha** para o **Linux Download Manager (LDM)**.

Ao adotar este conjunto autoral, o LDM elimina completamente a dependência de temas de terceiros instalados no sistema (como WhiteSur, Adwaita clássico ou Breeze), garantindo que o programa tenha a mesma aparência consistente em qualquer distribuição Linux ou Steam Deck.

---

## 📐 Especificações de Design
- **Grade base:** 24×24 px (`viewBox="0 0 24 24"`).
- **Espessura do traço:** 2 px uniforme (`stroke-width="2"`).
- **Terminações e junções:** Arredondadas (`stroke-linecap="round"`, `stroke-linejoin="round"`).
- **Cor Primária:** Vermelho Rubro / Crimson Neon (`#F43F5E`).
- **Destaque Vídeo:** Âmbar (`#F59E0B`) específico para `video-x-generic`.

---

## 📋 Mapeamento dos 21 Ícones

### 1. Barra de Ferramentas Principal
| Arquivo | Nome | Ação no LDM |
|---|---|---|
| `list-add.svg` | Adicionar URL | Abre diálogo para inserir novo link de download |
| `video-x-generic.svg` | Baixar Vídeo | Captura e download de vídeo/stream (destaque em âmbar `#F59E0B`) |
| `media-playback-start.svg` | Retomar | Inicia ou retoma downloads selecionados |
| `media-playback-pause.svg` | Pausar | Pausa downloads ativos selecionados |
| `media-playback-stop.svg` | Parar Todos | Interrompe imediatamente todas as conexões ativas |
| `edit-delete.svg` | Excluir | Remove download da fila ou do disco |
| `edit-clear-all.svg` | Limpar Concluídos | Limpa itens concluídos da lista |
| `preferences-system.svg` | Opções | Abre janela de configurações e preferências |
| `alarm-symbolic.svg` | Agendador (Simbólico) | Agendamento de downloads |
| `appointment-new.svg` | Agendador (Novo) | Criação de novo agendamento |
| `go-next.svg` | Iniciar Fila | Inicia o processamento sequencial da fila |
| `process-stop.svg` | Parar Fila | Pausa o processamento da fila de downloads |
| `speedometer.svg` | Limitador de Velocidade | Ativa/desativa limite global de banda |
| `network-wireless.svg` | Conexão de Rede | Ícone alternativo para limitador/rede |
| `network-server.svg` | Grabber | Capturador de sites e links recursivos |

### 2. Árvore Lateral (Categorias)
| Arquivo | Nome | Seção |
|---|---|---|
| `folder.svg` | Todos | Categoria geral de downloads |
| `folder-download.svg` | Downloads | Downloads em andamento e concluídos |
| `folder-documents.svg` | Documentos | Categoria de arquivos de texto/documentos |
| `view-list.svg` | Lista de Filas | Visualização das filas de download |
| `view-list-symbolic.svg` | Filas (Simbólico) | Indicador compacto de fila |

### 3. Lista e Janelas
| Arquivo | Nome | Uso |
|---|---|---|
| `text-x-generic.svg` | Arquivo Genérico | Ícone padrão para tipos de arquivo desconhecidos |

---

## 📦 Formatos Disponíveis por Ícone
Para cada ícone foram gerados:
1. `.svg` — Vetor original limpo para GTK e Cairo.
2. `.png` (24×24 px) — Resolução padrão 1x.
3. `@2x.png` (48×48 px) — Alta densidade (HiDPI / telas 4K / Steam Deck).

