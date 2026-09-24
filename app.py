from functools import lru_cache
from io import StringIO
from pathlib import Path
from threading import Lock
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request, Response
from plotly.offline import get_plotlyjs

import avaliacao as historical
import eleicoes2026 as current

ROOT     = Path(__file__).resolve().parent
SOURCE   = ROOT/'data/data.csv'
METHODS  = ['simple','latest_10','weighted']
SELECTED = ['SP','MG','RJ','BA','PR','RS','PE','CE','PA']
LOCK     = Lock()
app      = Flask(__name__,template_folder='tracker_web',static_folder='tracker_web/static')


@lru_cache(maxsize=4)
def election_results(year):
    return current.import_election_results(year)


@lru_cache(maxsize=8)
def prepared_data(year,modified,day):
    """Load prepared surveys and registry metadata for a source revision.

    Parameters
    ----------
    year : int
        Election year.
    modified : int
        CSV modification time, used to invalidate the cache.
    day : str
        Current date, used to refresh the live calendar.

    Returns
    -------
    tuple
        National surveys, state surveys and their combined registry table.
    """
    module = current if year == 2026 else historical
    national, states = module.import_prepared_data(year=year,source=SOURCE,show=False)
    lines = []
    for line in SOURCE.read_bytes().splitlines(keepends=True):
        try:
            lines.append(line.decode('utf-8'))
        except UnicodeDecodeError:
            lines.append(line.decode('cp1252'))
    raw = pd.read_csv(StringIO(''.join(lines)),low_memory=False)
    raw = raw.loc[raw['ano']==year].copy()

    raw['sigla_uf'] = raw['sigla_uf'].fillna('BR')
    raw['data']     = pd.to_datetime(raw['data']).dt.normalize()
    surveys = pd.concat([national]+list(states.values()),ignore_index=True)
    keys    = ['data','sigla_uf','instituto','id_pesquisa']
    for frame in [raw,surveys]:
        frame['id_pesquisa'] = frame['id_pesquisa'].astype(str).str.replace(r'\.0$','',regex=True)
    registry = raw.groupby(keys)['numero_registro'].agg(lambda x:' / '.join(sorted(set(x.dropna().astype(str)))))
    surveys  = surveys.merge(registry.rename('registry'),on=keys,how='left',validate='one_to_one')
    return national, states, surveys


def records(frame):
    return json.loads(frame.to_json(orient='records',date_format='iso'))


@lru_cache(maxsize=24)
def dashboard(year,method,modified,day):
    """Build dashboard data from the existing analysis functions.

    Parameters
    ----------
    year : int
        2014, 2018, 2022 or 2026.
    method : str
        Poll aggregation method.
    modified : int
        Source modification timestamp for cache invalidation.
    day : str
        Current date for cache invalidation.

    Returns
    -------
    dict
        Daily trackers, diagnostics, contributions, surveys and performance.
    """
    module = current if year == 2026 else historical
    candidates, dates = module.election_settings(year)
    national_polls, state_polls, surveys = prepared_data(year,modified,day)
    previous = election_results(year-4)
    weights  = previous.set_index('sigla_uf')['valid_votes']
    national = module.aggregate_polls(national_polls,method=method,year=year)
    states   = {uf:module.aggregate_polls(frame,method=method,year=year) for uf,frame in state_polls.items()}
    completed = module.fill_state_trackers(states,previous,fill_type='previous',year=year,show=False)
    aggregate = module.aggregate_states(completed,weights,year=year)
    composition = module.pollster_composition(national_polls,state_polls,year=year)
    common = composition.index[(composition['national']>0) & (composition['state']>0)].tolist()
    matched = module.aggregate_polls(national_polls.loc[national_polls['instituto'].isin(common)],method=method,year=year)
    coverage, figure = module.state_poll_coverage(states,weights,year=year)
    plt.close(figure)
    coverage = coverage.set_index('data')
    weights  = weights.reindex(module.GEOGRAPHIES)/weights.sum()
    shares   = pd.DataFrame({uf:frame.set_index('data')[candidates[0]] for uf,frame in completed.items()})
    actual   = None
    performance = []
    if year == 2026:
        components = 100*shares.diff().mul(weights,axis=1)
        eligible   = components.notna().all(axis=1) & components.abs().gt(1e-12).any(axis=1)
        total      = 100*aggregate.set_index('data')[candidates[0]].diff()
    else:
        results = election_results(year)
        actual  = results.set_index('sigla_uf').reindex(module.GEOGRAPHIES)
        current_weights = actual['valid_votes']/actual['valid_votes'].sum()
        components = 100*shares.sub(actual[candidates[0]],axis=1).mul(weights,axis=1)
        eligible   = components.notna().all(axis=1)
        total      = 100*(aggregate.set_index('data')[candidates[0]]-(actual[candidates[0]]*current_weights).sum())
        accuracy   = module.pollster_accuracy(national_polls,state_polls,results,year=year)
        accuracy   = accuracy.pivot(index='Institute',columns='Level',values='Average absolute error (pp)')
        table      = composition.copy()

        table['national_error'] = accuracy.reindex(columns=['National'])['National']
        table['state_error']    = accuracy.reindex(columns=['State'])['State']
        performance = records(table.rename_axis('institute').reset_index())
    contributions = components.loc[eligible,SELECTED].copy()
    others = [uf for uf in module.GEOGRAPHIES if uf not in SELECTED]

    contributions['Others'] = components.loc[eligible,others].sum(axis=1)
    if actual is not None:
        contributions['Voting-weight change'] = 100*((weights-current_weights)*actual[candidates[0]]).sum()
    np.testing.assert_allclose(contributions.sum(axis=1),total.loc[eligible],atol=1e-10,rtol=0)
    contributions['Total'] = total.loc[eligible]
    daily = pd.DataFrame({'data':dates})
    for key,frame in [('national',national),('aggregate',aggregate),('matched',matched)]:
        for i,candidate in enumerate(candidates):
            daily[f'{key}_{i}'] = 100*frame[candidate].to_numpy()
    daily['coverage']  = coverage['coverage_pct'].to_numpy()
    daily['freshness'] = coverage['latest_poll_age_days'].to_numpy()
    state_data = {}
    for uf,frame in completed.items():
        table = frame[['data']+candidates].copy()
        table = table.rename(columns=dict(zip(candidates,['share_0','share_1'])))

        table[['share_0','share_1']] *= 100
        table['polled'] = states[uf][candidates].notna().all(axis=1).to_numpy() if uf in states else False
        state_data[uf] = records(table)
    polls = surveys.loc[surveys['data'].between(pd.Timestamp(year=year,month=8,day=3),dates[-1])].copy()
    polls = polls.rename(columns={'instituto':'institute','sigla_uf':'coverage',candidates[0]:'share_0',candidates[1]:'share_1'})

    polls[['share_0','share_1']] *= 100
    return {
        'year':year,'method':method,'candidates':candidates,'start':str(dates[0].date()),'end':str(dates[-1].date()),
        'daily':records(daily),'states':state_data,'common':common,
        'contributions':records(contributions.rename_axis('data').reset_index()),
        'polls':records(polls[['data','institute','coverage','share_0','share_1','registry','id_pesquisa']]),
        'performance':performance,'actual':None if actual is None else [float(100*(actual[name]*current_weights).sum()) for name in candidates],
        'state_actual':{} if actual is None else {uf:[float(100*actual.loc[uf,name]) for name in candidates] for uf in actual.index}
    }


@app.get('/')
def index():
    return render_template('index.html')


@app.get('/plotly.js')
def plotly_script():
    return Response(get_plotlyjs(),mimetype='application/javascript',headers={'Cache-Control':'public, max-age=86400'})


@app.get('/api/dashboard')
def api_dashboard():
    year   = request.args.get('year',2026,type=int)
    method = request.args.get('method','latest_10')
    if year not in [2014,2018,2022,2026] or method not in METHODS:
        return jsonify(error='Select a supported election and aggregation method.'),400
    try:
        with LOCK:
            data = dashboard(year,method,SOURCE.stat().st_mtime_ns,str(pd.Timestamp.today().date()))
        return jsonify(data)
    except Exception:
        app.logger.exception('Could not build dashboard')
        return jsonify(error='Could not load the election data. Check the server log and local source files, then retry.'),500


if __name__ == '__main__':
    app.run(host='127.0.0.1',port=5000,debug=False)
