#!/usr/bin/env python3
import argparse, math, re, sqlite3, zipfile, tempfile, shutil
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

PHASE_CODES = ['IC1','FC1','IN1','FN1','IP1','FP1','IR1','FR1']

def resolve_input(path: Path):
    path = Path(path)
    if path.suffix.lower() == '.zip':
        tmp = Path(tempfile.mkdtemp(prefix='vallen_'))
        with zipfile.ZipFile(path) as z:
            z.extractall(tmp)
        pr = list(tmp.rglob('*.pridb'))
        va = list(tmp.rglob('*.vaex'))
        return pr[0], (va[0] if va else None), tmp
    return path, (path.with_suffix('.vaex') if path.with_suffix('.vaex').exists() else None), None

def get_pressure_scaling(vaex_path):
    # Defaults observed in Vallen VAEX: Pressure input offset 1000, factor 0.00625
    offset, factor = 1000.0, 0.00625
    if vaex_path and Path(vaex_path).exists():
        try:
            root = ET.parse(vaex_path).getroot()
            for inp in root.iter():
                if inp.tag.endswith('Input') and (inp.attrib.get('LongName','').lower() == 'pressure' or inp.attrib.get('Name','').lower() in ('press','pressure')):
                    offset = float(inp.attrib.get('Offset', offset))
                    factor = float(inp.attrib.get('Factor', factor))
                    break
        except Exception:
            pass
    return offset, factor

def extract(pridb_path, vaex_path=None):
    offset, factor = get_pressure_scaling(vaex_path)
    con = sqlite3.connect(str(pridb_path))
    con.row_factory = sqlite3.Row
    # Acquisition absolute date/time
    acq_start = None
    for r in con.execute('select Data from ae_markers order by SetID'):
        if r['Data']:
            m = re.search(r'(20\d\d-\d\d-\d\d \d\d:\d\d:\d\d)', r['Data'])
            if m:
                acq_start = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
                break
    # Markers
    markers = {}
    marker_rows = []
    for r in con.execute('select SetID, Number, Data, SetType, Time from view_ae_markers order by SetID'):
        txt = r['Data'] or ''
        code = None
        m = re.search(r'\b(' + '|'.join(PHASE_CODES) + r')\b', txt)
        if m:
            code = m.group(1)
            markers[code] = float(r['Time'])
        marker_rows.append({'SetID': r['SetID'], 'Number': r['Number'], 'Data': txt, 'Time_s': float(r['Time']), 'Code': code})
    # Pressure points
    pressure_points = []
    for r in con.execute('select Time, PA0 from view_ae_data where PA0 is not null order by Time'):
        p = (float(r['PA0']) - offset) * factor
        pressure_points.append((float(r['Time']), p, float(r['PA0'])))
    def nearest_pressure(t):
        if not pressure_points: return (None, None, None)
        return min(pressure_points, key=lambda x: abs(x[0] - t))
    # Hits
    hits = []
    for r in con.execute('select Time, Chan, Amp, Dur, Eny, RMS, Counts, TRAI from view_ae_data where Amp is not null order by Time'):
        amp_uv = float(r['Amp']) if r['Amp'] is not None else None
        amp_db = 20*math.log10(amp_uv) if amp_uv and amp_uv > 0 else None
        pp = nearest_pressure(float(r['Time']))
        hits.append({'Time_s': float(r['Time']), 'Chan': r['Chan'], 'Amp_uV': amp_uv, 'Amp_dB': amp_db, 'Dur_us': r['Dur'], 'Energy_eu': r['Eny'], 'RMS_uV': r['RMS'], 'Counts': r['Counts'], 'TRAI': r['TRAI'], 'Pressure_bar': pp[1]})
    def phase_stats(a,b):
        if a not in markers or b not in markers:
            return {}
        t0,t1 = markers[a], markers[b]
        subset=[h for h in hits if t0 <= h['Time_s'] <= t1 and h['Chan'] in (1,2)]
        pp=[p for p in pressure_points if t0 <= p[0] <= t1]
        return {
            'start_marker': a, 'end_marker': b, 'start_s': t0, 'end_s': t1, 'duration_s': t1-t0,
            'start_time': (acq_start + timedelta(seconds=t0)).strftime('%H:%M:%S') if acq_start else '',
            'end_time': (acq_start + timedelta(seconds=t1)).strftime('%H:%M:%S') if acq_start else '',
            'pressure_start_bar': nearest_pressure(t0)[1], 'pressure_end_bar': nearest_pressure(t1)[1],
            'pressure_min_bar': min([p[1] for p in pp], default=None), 'pressure_max_bar': max([p[1] for p in pp], default=None),
            'hits': len(subset),
            'max_amp_dB': max([h['Amp_dB'] for h in subset if h['Amp_dB'] is not None], default=None),
            'max_rms_uV': max([h['RMS_uV'] for h in subset if h['RMS_uV'] is not None], default=None),
            'events_ge_75dB': sum(1 for h in subset if h['Amp_dB'] is not None and h['Amp_dB'] >= 75),
            'events_ge_85dB': sum(1 for h in subset if h['Amp_dB'] is not None and h['Amp_dB'] >= 85),
        }
    phases = {
        'Funzionalita iniziale IC1-FC1': phase_stats('IC1','FC1'),
        'Rumore fondo iniziale IN1-FN1': phase_stats('IN1','FN1'),
        'Pressurizzazione IP1-FP1': phase_stats('IP1','FP1'),
        'Fondo finale IR1-FR1': phase_stats('IR1','FR1'),
    }
    p_phase = phases['Pressurizzazione IP1-FP1']
    delta_p = (p_phase.get('pressure_end_bar') or 0) - (p_phase.get('pressure_start_bar') or 0)
    grad = delta_p / (p_phase.get('duration_s')/60) if p_phase.get('duration_s') else None
    con.close()
    return {
        'file': Path(pridb_path).name,
        'acq_start': acq_start.strftime('%Y-%m-%d %H:%M:%S') if acq_start else '',
        'date': acq_start.strftime('%Y-%m-%d') if acq_start else '',
        'markers': marker_rows,
        'phases': phases,
        'summary': {
            'matricola_inferita': '50711' if '50711' in Path(pridb_path).name else '',
            'provincia_inferita': 'MC' if Path(pridb_path).stem.upper().endswith('MC_EA') else '',
            'pressione_inizio_bar': p_phase.get('pressure_start_bar'),
            'pressione_fine_bar': p_phase.get('pressure_end_bar'),
            'pressione_max_bar': p_phase.get('pressure_max_bar'),
            'delta_p_bar': delta_p,
            'gradiente_bar_min': grad,
            'ora_inizio_acquisizione': acq_start.strftime('%H:%M') if acq_start else '',
            'ora_inizio_pressurizzazione': p_phase.get('start_time','')[:5],
            'ora_fine_pressurizzazione': p_phase.get('end_time','')[:5],
            'hits_pressurizzazione': p_phase.get('hits'),
            'max_amp_pressurizzazione_dB': p_phase.get('max_amp_dB'),
            'max_rms_pressurizzazione_uV': p_phase.get('max_rms_uV'),
            'fondo_finale_hits': phases['Fondo finale IR1-FR1'].get('hits'),
            'fondo_finale_max_amp_dB': phases['Fondo finale IR1-FR1'].get('max_amp_dB'),
            'fondo_finale_max_rms_uV': phases['Fondo finale IR1-FR1'].get('max_rms_uV'),
            'fondo_finale_eventi_ge_75dB': phases['Fondo finale IR1-FR1'].get('events_ge_75dB'),
            'fondo_finale_eventi_ge_85dB': phases['Fondo finale IR1-FR1'].get('events_ge_85dB'),
            'gamma_max': None,
            'gamma_note': 'Non presente come campo salvato nel PRIDB standard: serve esportazione BD/listato Vallen o API VisualAE/AMSY per acquisire il valore calcolato.'
        }
    }

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('input', help='File .zip Vallen oppure .pridb')
    ap.add_argument('--out', default='vallen_summary.csv')
    args = ap.parse_args()
    pridb, vaex, tmp = resolve_input(Path(args.input))
    data = extract(pridb, vaex)
    s = data['summary']
    keys = list(s.keys())
    with open(args.out,'w',encoding='utf-8') as f:
        f.write(';'.join(keys)+'\n')
        f.write(';'.join('' if s[k] is None else str(s[k]).replace('.',',') for k in keys)+'\n')
    if tmp: shutil.rmtree(tmp, ignore_errors=True)
    print(f'Scritto {args.out}')
