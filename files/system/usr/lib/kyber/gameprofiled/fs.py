"""
KYBER — raiz de filesystem injetável.

Todo acesso a /sys e /proc passa por aqui, e a razão é uma só: os testes
rodam num Mac. Uma árvore falsa em /tmp responde às mesmas perguntas que
o sysfs de verdade, e a descoberta de sensores — que é o coração deste
daemon — fica exercitável sem hardware.

`show()` existe por causa disso: o caminho publicado no state.json e no
log tem que ser o que o SISTEMA vê (/sys/class/hwmon/hwmon3/...), não o
que o teste montou (/tmp/pytest-xyz/sys/class/hwmon/hwmon3/...).
"""

from pathlib import Path


class Fs:
    def __init__(self, root="/"):
        self.root = Path(root)

    def path(self, rel):
        return self.root / str(rel).lstrip("/")

    def show(self, p):
        """O caminho como o sistema o vê, sem a raiz de teste na frente."""
        try:
            return "/" + str(Path(p).relative_to(self.root))
        except ValueError:
            return str(p)

    def glob(self, pattern):
        return sorted(self.root.glob(str(pattern).lstrip("/")))

    def exists(self, p):
        return Path(p).exists()

    # ------------------------------------------------------------------
    # Leitura.
    #
    # sysfs devolve EACCES, ENODEV, EIO e ETIMEDOUT em situações
    # perfeitamente normais — driver descarregado, sensor ocupado, GPU em
    # suspensão. Nenhuma delas é motivo para derrubar o daemon, e todas
    # significam a mesma coisa para quem lê: não há valor. Devolver None
    # é o que permite publicar ausência em vez de zero.
    # ------------------------------------------------------------------
    def read(self, p):
        try:
            return Path(p).read_text(errors="replace").strip()
        except OSError:
            return None

    def read_bytes(self, p):
        try:
            return Path(p).read_bytes()
        except OSError:
            return None

    def read_int(self, p):
        texto = self.read(p)
        if texto is None:
            return None
        try:
            return int(texto.split()[0])
        except (ValueError, IndexError):
            return None

    def write(self, p, valor):
        """Devolve None em caso de sucesso, ou a mensagem do erro.

        Escrever em sysfs falha de formas que importam distinguir: EACCES
        é permissão, EINVAL é valor recusado pelo driver, ENODEV é o nó
        que sumiu. A mensagem vai para o log e para a nota do eixo."""
        try:
            with open(p, "w") as arquivo:
                arquivo.write(str(valor))
            return None
        except OSError as erro:
            return f"{type(erro).__name__}: {erro.strerror or erro}"
