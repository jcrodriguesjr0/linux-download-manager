"""Tradução mínima: interface nativa em PT-BR, com inglês para menus, barra de ferramentas e colunas."""
_LANG = "pt"

EN = {
    "Tarefas": "Tasks", "Arquivo": "File", "Downloads": "Downloads", "Exibir": "View", "Ajuda": "Help",
    "Adicionar URL": "Add URL", "Retomar": "Resume", "Parar": "Stop", "Parar todos": "Stop all",
    "Excluir": "Delete", "Excluir concluídos": "Delete completed", "Opções": "Options",
    "Agendador": "Scheduler", "Iniciar fila": "Start queue", "Parar fila": "Stop queue",
    "Grabber": "Grabber", "Nome do arquivo": "File name", "Tamanho": "Size", "Status": "Status",
    "Tempo restante": "Time left", "Velocidade": "Transfer rate", "Última tentativa": "Last try date",
    "Descrição": "Description", "Todos os downloads": "All downloads", "Incompletos": "Unfinished",
    "Concluídos": "Finished", "Filas": "Queues", "Projetos do Grabber": "Grabber projects",
    "Na fila": "Queued", "Conectando": "Connecting", "Baixando": "Downloading", "Pausado": "Paused",
    "Concluído": "Complete", "Erro": "Error", "Adicionar download em lote": "Add batch download",
    "Executar Site Grabber": "Run site grabber", "Exportar": "Export", "Importar": "Import",
    "Limitador de velocidade": "Speed Limiter", "Ligar": "Turn on", "Desligar": "Turn off",
    "Configurações...": "Settings...", "Sair": "Exit", "Sobre o LDM": "About LDM", "Pesquisar": "Search",
    "Iniciar download": "Start download", "Baixar depois": "Download later", "Cancelar": "Cancel",
    "Geral": "General", "Compactados": "Compressed", "Documentos": "Documents", "Músicas": "Music",
    "Programas": "Programs", "Vídeos": "Video", "Modo escuro": "Dark mode", "Idioma": "Language",
}


def set_language(lang: str):
    global _LANG
    _LANG = lang


def _(s: str) -> str:
    return EN.get(s, s) if _LANG == "en" else s
