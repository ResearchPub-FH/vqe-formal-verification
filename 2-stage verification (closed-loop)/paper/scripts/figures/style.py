"""Common publication dimensions and typography (no experimental values)."""
from pathlib import Path
import os
os.environ.setdefault('MPLCONFIGDIR', '/private/tmp/vqe-paper-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

PAPER=Path(__file__).resolve().parents[2]
EXP=PAPER.parent
WORK=EXP.parent
RUN=EXP/'artifacts/approved-experiment'
plt.rcParams.update({
    'font.family':'DejaVu Sans','font.size':8,'axes.labelsize':8.5,
    'xtick.labelsize':7.5,'ytick.labelsize':7.5,'legend.fontsize':7.1,
    'axes.spines.top':False,'axes.spines.right':False,
    'axes.linewidth':.6,'lines.linewidth':1.1,
    'pdf.fonttype':42,'ps.fonttype':42,'savefig.pad_inches':.03,
    'axes.formatter.useoffset':False,
})
BLUE='#235789'; ORANGE='#b55224'; GRAY='#777777'
def export(fig,name):
    (PAPER/'figures').mkdir(exist_ok=True)
    fig.savefig(PAPER/'figures'/name,format='pdf')
    plt.close(fig)
