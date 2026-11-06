#!/usr/bin/env python3
"""Gurobi nonconvex comparison using the same polynomial specifications."""

import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

import gurobipy as gp
from gurobipy import GRB
import psutil

import nra_irrational_20261102 as spec
from nra_public_20261102 import LIMIT, number, save, starting_point


def main():
    psutil.Process().cpu_affinity([int(os.environ.get("OMT_NRA_CORE", "12"))])
    for path in sorted((spec.OUT/'models').glob('*.json')):
        data=json.loads(path.read_text());folder=spec.OUT/'gurobi'/data['name'];folder.mkdir(parents=True,exist_ok=True)
        if (folder/'result.json').exists():continue
        m=gp.Model();m.Params.Threads=1;m.Params.TimeLimit=LIMIT;m.Params.MemLimit=4;m.Params.NonConvex=2
        m.Params.MIPGap=1e-8;m.Params.MIPGapAbs=1e-8;m.Params.FeasibilityTol=1e-8;m.Params.OptimalityTol=1e-8
        m.Params.BarQCPConvTol=1e-8;m.Params.LogFile=str(folder/'solver.log')
        vs=[m.addVar(lb=number(v['lb']),ub=number(v['ub']),name=f'x{i}') for i,v in enumerate(data['variables'])]
        def expression(poly):
            result=gp.QuadExpr(number(poly['constant']))
            for coefficient,ids in poly['terms']:
                term=number(coefficient)*vs[ids[0]]
                if len(ids)==2:term*=vs[ids[1]]
                result+=term
            return result
        for c in data['constraints']:
            e,lo,hi=expression(c),number(c['lb']),number(c['ub'])
            if lo==hi:m.addQConstr(e==lo)
            else:
                if lo!=-float('inf'):m.addQConstr(e>=lo)
                if hi!=float('inf'):m.addQConstr(e<=hi)
        if data['family']=='C':
            p=data['parameters'];b=m.addVar(vtype=GRB.BINARY,name='branch')
            m.addQConstr(vs[0]*vs[0]+vs[1]*vs[1]>=p['r0']+(p['r1']-p['r0'])*b)
            m.addConstr(vs[1]<=1+(p['u']-1)*b)
            m.addConstr(vs[0]<=p['u']-(p['u']-1)*b)
        m.setObjective(expression(data['objective']),GRB.MINIMIZE)
        for v,start in zip(vs,starting_point(data)):v.Start=start
        t=time.monotonic();m.optimize();elapsed=time.monotonic()-t
        x=[v.X for v in vs] if m.SolCount else None
        checked=spec.assess(data,x,data['reference'])
        record=dict(solver='gurobi',instance=data['name'],status=str(m.Status),elapsed_s=elapsed,
            timeout_s=LIMIT,core=int(os.environ.get("OMT_NRA_CORE", "12")),x=x,optimization_hit=checked['reference_hit'],
            model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),**checked)
        save(folder/'result.json',record);print(data['name'],record['optimization_hit'],checked.get('objective'),flush=True)
        m.dispose()
    save(spec.OUT/'gurobi-environment.json',dict(version=list(gp.gurobi.version()),python=sys.version,
        platform=platform.platform(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__=='__main__':main()
