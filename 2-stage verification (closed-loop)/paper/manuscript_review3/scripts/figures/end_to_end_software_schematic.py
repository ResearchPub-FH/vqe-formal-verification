#!/usr/bin/env python3
"""Illustrative software schematic of the implemented VQE verification system.

This is a standalone figure proposal. It does not edit the main manuscript or
replace its figures. Icons represent components and mathematical objects, not
measured results. Source APIs, event names and artifacts are checked below.
"""
from pathlib import Path
import ast
import hashlib
import json
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Polygon, Rectangle
from matplotlib.lines import Line2D
import numpy as np

REV = Path(__file__).resolve().parents[2]
PAPER = REV.parent
EXPERIMENT = PAPER.parent
OUT = REV / 'figures'
STEM = 'end-to-end-software-schematic'

INK = '#173049'
MUTED = '#506275'
LINE = '#C8D3DF'
BLUE = '#165AC1'
ORANGE = '#C05216'
PURPLE = '#7255B8'
GREEN = '#16775C'
FILLBLUE = '#EEF4FF'
FILLO = '#FFF5ED'
FILLGREEN = '#F0F8F4'
WHITE = '#FFFFFF'

plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 16,
                     'pdf.fonttype': 42, 'svg.fonttype': 'none',
                     'savefig.facecolor': WHITE})
fig, ax = plt.subplots(figsize=(14.4, 13.6))
fig.subplots_adjust(0, 0, 1, 1)
ax.set(xlim=(0, 1440), ylim=(1190, 0))
ax.axis('off')
texts = []

def text(x, y, value, size=16, color=INK, weight='normal', ha='left', va='center', mono=False, **kwargs):
    kwargs.setdefault('zorder', 6)
    obj = ax.text(x, y, value, fontsize=size, color=color, weight=weight,
                  ha=ha, va=va, family='DejaVu Sans Mono' if mono else 'DejaVu Sans',
                  linespacing=1.4, **kwargs)
    texts.append(obj)
    return obj

def box(x, y, w, h, fill=WHITE, stroke=LINE, radius=9, lw=1, zorder=2):
    obj = FancyBboxPatch((x, y), w, h, boxstyle=f'round,pad=0,rounding_size={radius}',
                         facecolor=fill, edgecolor=stroke, linewidth=lw, zorder=zorder)
    ax.add_patch(obj)
    return obj

def line(points, color=INK, width=1.25, style='solid', zorder=3):
    xs, ys = zip(*points)
    ax.add_line(Line2D(xs, ys, color=color, linewidth=width, linestyle=style, zorder=zorder))

def arrow(points, color=INK, width=1.25, style='solid', zorder=3):
    if len(points) > 2:
        line(points[:-1], color, width, style, zorder)
    ax.add_patch(FancyArrowPatch(points[-2], points[-1], arrowstyle='-|>', mutation_scale=12,
                               linewidth=width, color=color, linestyle=style, zorder=zorder))

def pill(x, y, w, value, color=BLUE, fill=FILLBLUE, size=15):
    box(x, y, w, 29, fill, color, radius=6, lw=.7)
    text(x+w/2, y+14.5, value, size, color, 'bold', ha='center')

def document(x, y, color=BLUE, scale=1):
    w, h = 27*scale, 34*scale
    ax.add_patch(Polygon([(x,y),(x+w-8*scale,y),(x+w,y+8*scale),(x+w,y+h),(x,y+h)],
                         closed=True, facecolor=WHITE, edgecolor=color, linewidth=1.15, zorder=4))
    line([(x+w-8*scale,y),(x+w-8*scale,y+8*scale),(x+w,y+8*scale)],color)
    for yy in [14,21,28]: line([(x+5*scale,y+yy*scale),(x+w-5*scale,y+yy*scale)],color,.8)

def band(y, h, title, fill, color, subtitle=None):
    box(22, y, 1396, h, fill, fill, radius=14, lw=0, zorder=0)
    text(40, y+23, title, 21, color, 'bold')
    if subtitle:
        text(1400, y+23, subtitle, 14, MUTED, ha='right')

def circuit(x, y, w=211):
    for yy, label in [(y,'q0'),(y+26,'q1')]:
        text(x, yy, label, 14, MUTED)
        line([(x+30,yy),(x+w,yy)],BLUE,.95)
    for offset,label in [(40,'H'),(65,'$R_z$'),(90,'Y'),(141,'H'),(166,'$R_z$'),(191,'Y')]:
        xx=x+offset
        for yy in [y,y+26]:
            box(xx-10.5,yy-10,21,20,FILLBLUE,BLUE,radius=3,lw=.7,zorder=4)
            text(xx,yy,label,12,BLUE,ha='center',zorder=5)
    line([(x+117,y),(x+117,y+26)],BLUE,1.2)
    ax.add_patch(Circle((x+117,y),3,facecolor=BLUE,zorder=5))
    ax.add_patch(Circle((x+117,y+26),7,facecolor=WHITE,edgecolor=BLUE,lw=1,zorder=5))
    line([(x+117,y+20),(x+117,y+32)],BLUE,.9, zorder=6)
    line([(x+111,y+26),(x+123,y+26)],BLUE,.9, zorder=6)

def controller_icon(x, y):
    for i, label in enumerate(['M','A','V','C']):
        xx=x+46*i
        if i: arrow([(xx-30,y),(xx-13,y)],BLUE,.8)
        ax.add_patch(Circle((xx,y),12,facecolor=FILLBLUE,edgecolor=BLUE,lw=1,zorder=4))
        text(xx,y,label,14,BLUE,ha='center',weight='bold')

def dtmc_icon(x, y):
    # Illustrative finite-state transition topology, without result values.
    pts=[(x,y+10),(x+61,y-8),(x+122,y+10)]
    for a,b in [(0,1),(1,2),(1,0)]: arrow([pts[a],pts[b]],BLUE,.8)
    for i,pt in enumerate(pts):
        ax.add_patch(Circle(pt,9,facecolor=FILLBLUE,edgecolor=BLUE,lw=.9,zorder=4))
    ax.add_patch(FancyArrowPatch((x+123,y+1),(x+130,y+16),connectionstyle='arc3,rad=-2.2',
                               arrowstyle='-|>',mutation_scale=8,color=BLUE,lw=.8,zorder=4))

def source_functions(relative):
    tree=ast.parse((EXPERIMENT/relative).read_text())
    return {n.name for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.ClassDef))}

def main():
    OUT.mkdir(exist_ok=True)
    required = {
        'closed_loop/pre_execution.py': ['run_pre_execution'],
        'closed_loop/logical.py': ['model'],
        'closed_loop/execution.py': ['execute_run','execution_values','emit','run_baseline','replay'],
        'closed_loop/physics.py': ['point','candidate_indices','build_gaussian','export_dtmc'],
        'closed_loop/checker.py': ['RuntimeChecker','consume','reconstruct'],
        'closed_loop/temporal.py': ['build_monitor','project','verify_traces'],
        'closed_loop/comparison.py': ['compare','wilson','mean_interval'],
    }
    for filename,names in required.items():
        assert set(names)<=source_functions(filename),(filename,names)
    execution=(EXPERIMENT/'closed_loop/execution.py').read_text()
    event_names=['measurement','evaluation','numeric_valid','optimizer_commit','terminal']
    assert all(f'emit("{name}"' in execution for name in event_names)
    contracts=json.loads((EXPERIMENT/'config/contracts.json').read_text())
    assert set(contracts)=={f'{family}{i}' for family,limit in [('L',4),('N',4),('P',3)] for i in range(1,limit+1)}
    baseline_files={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in [REV/'manuscript_review3.tex', REV/'manuscript_review3.pdf', REV/'figures/architecture.pdf']}

    # Inputs: command surface, actual configuration, library and execution view.
    band(16,180,'Inputs and specifications','#F3F5F8',INK)
    box(40,57,247,119,'#223449','#223449')
    text(57,78,'>_  experiment.py',15,WHITE,'bold',mono=True)
    text(57,108,'pre / execute',14,'#DCEAFF',mono=True)
    text(57,133,'compare / audit',14,'#DCEAFF',mono=True)
    text(57,160,'--config  --output',13,'#B8CBDD',mono=True)
    box(304,57,344,126)
    document(322,74,BLUE,.85)
    text(366,86,'VQE instance',17,INK,'bold')
    text(322,115,'Hamiltonian / circuit / grid',14)
    text(322,140,'optimizer / shots / K / success',14)
    text(322,164,'config/h2.json',14,MUTED,mono=True)
    box(665,57,356,126)
    document(682,74,PURPLE,.85)
    text(725,86,'Specification library',18,INK,'bold')
    text(682,116,'L1-L4     N1-N4     P1-P3',16,PURPLE,'bold')
    text(682,142,'assumptions + runtime mappings',14)
    text(682,167,'config/contracts.json',14,MUTED,mono=True)
    box(1038,57,362,126)
    text(1056,82,'Shared execution model',17,INK,'bold')
    controller_icon(1080,114)
    text(1056,139,'phases / IDs / counters',15)
    text(1056,165,'controller + event context',14,MUTED)

    # Three distinct verification objects. Their outputs feed a recorded bundle.
    band(217,255,'Stage 1  |  Pre-execution verification',FILLBLUE,BLUE,
         'closed_loop.pre_execution')
    for x,w in [(40,284),(340,294),(650,348),(1022,378)]: box(x,262,w,172)
    text(57,284,'Logical adapter',18,BLUE,'bold')
    controller_icon(76,316)
    text(57,346,'controller.smv',15,mono=True)
    pill(57,364,102,'NuXmv')
    text(174,379,'order / epochs',14,MUTED)
    text(57,414,'nuxmv.log  ->  L1-L4',14,MUTED,mono=True)

    text(357,284,'Numeric adapter',18,BLUE,'bold')
    text(357,318,r'$A(x)\ \Longrightarrow\ Q(x,f(x))$',20,BLUE)
    text(357,348,'normalize / sum / grid',14)
    pill(357,364,90,'Dafny')
    text(461,379,'real / integer',14,MUTED)
    text(357,414,'proof logs -> N1-N4',14,MUTED)

    text(667,284,'Probabilistic adapter',18,BLUE,'bold')
    text(667,319,r'$\mathcal{N}(\mu,\sigma^2)$',23,BLUE)
    dtmc_icon(829,316)
    text(667,352,'Gaussian kernel -> DTMC (z,j)',14)
    pill(667,364,91,'Storm')
    pill(777,364,104,'Python',size=15)
    text(667,413,r'$p_G(k)$  /  $\mathrm{E}[T\mid T\leq K]$',16,MUTED)

    document(1039,278,BLUE)
    text(1082,290,'Verification record',18,BLUE,'bold')
    text(1039,326,'pre_execution.json',16,mono=True)
    text(1039,355,'configuration_digest',14,mono=True)
    text(1039,380,'sources / artifacts / assumptions',14)
    text(1039,410,'compiled monitor + provenance',14,MUTED,mono=True)
    for xx in [182,487,824]:
        line([(xx,434),(xx,451)],BLUE,1.0)
    arrow([(182,451),(1211,451),(1211,434)],BLUE,1.0)
    text(530,455,'verifier outputs + model predictions',14,BLUE,ha='center',
         bbox={'facecolor':FILLBLUE,'edgecolor':'none','pad':2})
    for xx in [476,843,1218]: arrow([(xx,196),(xx,217)],MUTED,1.0)

    # Source/configuration identity is checked before the executor runs.
    arrow([(1211,472),(1211,491),(960,491)],BLUE,1.1)
    pill(581,478,381,'verify record / sources / config',PURPLE,'#F3EEFD',14)
    arrow([(581,492),(178,492),(178,519)],PURPLE,1.1)

    # The implemented VQE computation and its concrete data interfaces.
    band(519,407,'Stage 2  |  Instrumented VQE execution',FILLO,ORANGE,
         None)
    text(1040,537,'execution / checker / temporal',13,MUTED)
    pill(1040,548,360,'faults: boundary / trace mutation',ORANGE,'#FFF9F2',14)
    yy,hh=580,136
    specs=[(40,210),(268,236),(522,234),(774,247),(1039,361)]
    for xx,ww in specs: box(xx,yy,ww,hh)
    text(55,601,'Candidates',17,INK,'bold')
    for i,value in enumerate(['z',r'$-$',r'$+$']):
        pill(55+i*61,625,53,value,PURPLE,'#F3EEFD',16)
    text(55,674,'current / - / +',14,MUTED)
    text(55,697,'candidate_indices',13,MUTED,mono=True)

    text(283,601,'Quantum kernel',17,INK,'bold')
    circuit(283,628)
    text(283,679,'state -> Born law',14,MUTED)
    text(283,704,'physics.point()',14,MUTED,mono=True)

    text(537,601,'Group sampling',17,INK,'bold')
    for i,label in enumerate(['ZI/ZZ','YZ','XX']):
        pill(537+i*69,623,63,label,ORANGE,'#FFF2E7',13)
    text(537,667,r'$[n_{00},n_{01},n_{10},n_{11}]$',16)
    text(537,695,'multinomial draws',14,MUTED)

    text(789,601,'Energy / score',17,INK,'bold')
    text(789,639,r'$\widehat E=\sum_i c_i\widehat e_i$',20,BLUE)
    text(789,672,'weighted Pauli terms',14,MUTED)
    text(789,697,'execution_values()',14,MUTED,mono=True)

    text(1054,601,'Optimizer / stop',18,INK,'bold')
    text(1054,635,r'$\arg\min\{s_0,s_{-},s_{+}\}$',18,PURPLE)
    text(1300,635,'ties: 0,-,+',13,MUTED)
    text(1054,667,'success / budget / abort',14)
    text(1054,695,'optimizer_commit / terminal',14,MUTED,mono=True)
    for a,b,label in [(250,268,r'$\theta$'),(504,522,'p'),(756,774,'n'),(1021,1039,'s')]:
        arrow([(a,646),(b,646)],INK,1.3)
        text((a+b)/2,625,label,14,MUTED,ha='center')
    arrow([(1218,716),(1218,731),(144,731),(144,716)],PURPLE,1.1)
    text(386,732,'next index / coordinate',14,PURPLE,ha='center',
         bbox={'facecolor':FILLO,'edgecolor':'none','pad':2})

    # Event taps from the sampled counts, reconstructed values, and commit/stop
    # boundary. Small gaps mark crossings with the optimizer's control return.
    for xx in [639,897,1360]:
        if xx < 1218:
            box(xx-4,727,8,8,FILLO,FILLO,radius=1,lw=0,zorder=3.5)
        arrow([(xx,716),(xx,752)],ORANGE,1.0,'dashed',zorder=4)

    box(40,752,1360,35,'#FBE6D6','#FBE6D6',radius=6,lw=0)
    text(57,770,'emit(kind, **data)',14,ORANGE,'bold',mono=True)
    text(287,770,'measurement  |  evaluation  |  numeric_valid  |  optimizer_commit  |  terminal',14,ORANGE,mono=True)

    box(40,814,554,93)
    text(56,833,'RuntimeChecker.consume(event)',16,ORANGE,'bold',mono=True)
    text(56,862,'Python online + replay: IDs / arithmetic / shots',14)
    text(56,888,'DejaVu: temporal-input.tsv / dejavu.log',14,MUTED)
    box(613,814,421,93)
    document(629,830,ORANGE,.85)
    text(671,838,'Trace store  |  *.jsonl.gz',16,INK,'bold')
    text(629,865,'run_id / evaluation_id',14,mono=True)
    text(629,889,'counts / shots / scores_used',13,MUTED)
    box(1053,814,347,93)
    document(1070,831,GREEN,.8)
    document(1076,825,GREEN,.8)
    text(1114,838,'Run summaries',16,INK,'bold')
    text(1070,866,'independent seeded streams',14)
    text(1070,889,'success_step / physical_shots',13,MUTED,mono=True)
    for xx in [317,823]: arrow([(xx,787),(xx,814)],ORANGE,1.1,'dashed')
    arrow([(75,814),(75,787)],PURPLE,1.0)
    text(84,802,'continue / stop',13,PURPLE)
    arrow([(613,883),(594,883)],ORANGE,1.0,'dashed')
    text(511,802,'online + persisted events',13,ORANGE,ha='center')
    arrow([(1034,858),(1053,858)],INK,1.1)

    # Comparison is distinct from the individual execution checks. No synthetic
    # measured values are drawn, and the post-audit interpretation is not equated
    # with the raw original comparator's marginal decision labels.
    band(949,192,'Cross-stage comparison and deliverables',FILLGREEN,GREEN,
         'comparison.py + statistical reporting')
    box(40,993,322,132)
    text(57,1015,'Match + agreement',18,GREEN,'bold')
    text(57,1043,'property + prospective scope',14)
    text(57,1068,'runtime check + assumptions',14)
    text(57,1094,'L1-L4 / N1-N4 verdicts',14,GREEN)
    box(380,993,348,132)
    text(397,1015,'Probability + resources',17,GREEN,'bold')
    text(397,1046,r'$p_G(k)$  vs.  $\widehat p(k)$',17)
    text(397,1074,'P2/P3: conditional means',14)
    text(397,1098,'Wilson / bootstrap / Holm',14,MUTED)
    box(746,993,320,132)
    text(763,1015,'Diagnostic results',18,GREEN,'bold')
    text(763,1044,'requirement + event ID',14)
    text(763,1069,'assumptions / missing inputs',14)
    text(763,1094,'verdict vector / fault traces',14,MUTED)
    box(1084,993,316,132)
    document(1101,1010,GREEN)
    text(1144,1023,'Report artifacts',18,GREEN,'bold')
    text(1101,1059,'REPORT.md',15,mono=True)
    text(1101,1084,'verdict_agreement.json',14,mono=True)
    text(1101,1108,'probabilities.csv',14,mono=True)
    # Runtime verdicts enter the deterministic comparison; first-success/resource
    # summaries enter the probabilistic comparison. Fault traces feed diagnostics.
    arrow([(317,907),(317,934),(17,934),(17,1050),(40,1050)],GREEN,1.05)
    arrow([(1226,907),(1226,936),(736,936),(736,1050),(728,1050)],GREEN,1.05)
    arrow([(823,907),(823,931),(906,931),(906,993)],ORANGE,1.0,'dashed')
    # Model/proof results feed both comparisons. These arrows do not express
    # equivalence among the verifier formalisms or a serial dependency between them.
    line([(1400,347),(1410,347),(1410,990),(201,990)],BLUE,.95,'dashed')
    for xx in [201,554]: arrow([(xx,990),(xx,993)],BLUE,.95,'dashed')
    text(1306,938,'Stage 1 record',13,BLUE,ha='center',
         bbox={'facecolor':FILLGREEN,'edgecolor':'none','pad':2})
    # Report packaging combines the three independently produced result families.
    for xx in [201,554,906]: line([(xx,1125),(xx,1133)],GREEN,1.0)
    arrow([(201,1133),(1242,1133),(1242,1125)],GREEN,1.05)

    text(40,1152,'A  agreement    D  disagreement    M  assumption mismatch    I  inconclusive',14,MUTED)
    arrow([(888,1152),(954,1152)],MUTED,1,'dashed')
    text(968,1152,'manual revision + new verification record',14,MUTED)
    text(40,1177,'Solid: module data / artifacts    Orange dashed: events / replay    Purple: control',13,MUTED)


    fig.canvas.draw()
    # Reject any text leaving the vector canvas. Visual QA covers card spacing.
    renderer=fig.canvas.get_renderer()
    bounds=fig.bbox
    outside=[]
    for obj in texts:
        bb=obj.get_window_extent(renderer)
        if bb.x0<bounds.x0 or bb.x1>bounds.x1 or bb.y0<bounds.y0 or bb.y1>bounds.y1:
            outside.append({'text':obj.get_text(),'box':list(bb.bounds),'canvas':list(bounds.bounds)})
    assert not outside, outside
    overlaps=[]
    for i,left in enumerate(texts):
        for right in texts[i+1:]:
            if left.get_window_extent(renderer).overlaps(right.get_window_extent(renderer)):
                overlaps.append((left.get_text(),right.get_text()))
    assert not overlaps, overlaps
    for suffix in ['pdf','svg','png']:
        fig.savefig(OUT/f'{STEM}.{suffix}',dpi=150,metadata={'Title':'End-to-end VQE verification software schematic'} if suffix=='pdf' else None)
    sources=[EXPERIMENT/f for f in required]+[EXPERIMENT/'experiment.py',EXPERIMENT/'config/contracts.json',EXPERIMENT/'config/h2.json',PAPER/'scripts/extract_results.py']
    sources += [EXPERIMENT/'formal'/name for name in ['VQELemmas.dfy','VQENumericKernels.dfy','GroupGrid.dfy','runtime.qtl']]
    manifest={'purpose':'Standalone illustrative proposal; not integrated into the manuscript',
              'intended_width':'double column, 7.2 inches; body text 7 pt, auxiliary labels 6.5 pt, circuit symbols 6 pt',
              'editable_source':str(Path(__file__).resolve().relative_to(REV)),
              'outputs':[f'figures/{STEM}.{s}' for s in ['pdf','svg','png']],
              'quantitative_results':'None; mathematical/object icons and symbolic field names only',
              'actual_apis_checked':required,'actual_event_names_checked':event_names,
              'source_sha256':{str(p.relative_to(EXPERIMENT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
              'existing_manuscript_and_architecture_hashes':baseline_files}
    (REV/'data/software_schematic_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name,expected in baseline_files.items():
        p=REV/('figures/'+name if name=='architecture.pdf' else name)
        assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
    print('Generated vector PDF/SVG and PNG preview; main manuscript and existing architecture unchanged.')

if __name__=='__main__':
    main()
