import random
from pypy.objspace.flow.model import FunctionGraph, Block, Link
from pypy.objspace.flow.model import SpaceOperation, Variable, Constant
from pypy.jit.codewriter import jitter
from pypy.jit.metainterp.history import getkind
from pypy.rpython.lltypesystem import lltype, rclass, rstr
from pypy.translator.unsimplify import varoftype

class FakeLink:
    args = []

def test_optimize_goto_if_not():
    v1 = Variable()
    v2 = Variable()
    v3 = Variable(); v3.concretetype = lltype.Bool
    sp1 = SpaceOperation('foobar', [], None)
    sp2 = SpaceOperation('foobaz', [], None)
    block = Block([v1, v2])
    block.operations = [sp1, SpaceOperation('int_gt', [v1, v2], v3), sp2]
    block.exitswitch = v3
    block.exits = exits = [FakeLink(), FakeLink()]
    res = jitter.optimize_goto_if_not(block)
    assert res == True
    assert block.operations == [sp1, sp2]
    assert block.exitswitch == ('int_gt', v1, v2)
    assert block.exits == exits

def test_optimize_goto_if_not__incoming():
    v1 = Variable(); v1.concretetype = lltype.Bool
    block = Block([v1])
    block.exitswitch = v1
    block.exits = [FakeLink(), FakeLink()]
    assert not jitter.optimize_goto_if_not(block)

def test_optimize_goto_if_not__exit():
    v1 = Variable()
    v2 = Variable()
    v3 = Variable(); v3.concretetype = lltype.Bool
    block = Block([v1, v2])
    block.operations = [SpaceOperation('int_gt', [v1, v2], v3)]
    block.exitswitch = v3
    block.exits = [FakeLink(), FakeLink()]
    block.exits[1].args = [v3]
    assert not jitter.optimize_goto_if_not(block)

def test_optimize_goto_if_not__unknownop():
    v3 = Variable(); v3.concretetype = lltype.Bool
    block = Block([])
    block.operations = [SpaceOperation('foobar', [], v3)]
    block.exitswitch = v3
    block.exits = [FakeLink(), FakeLink()]
    assert not jitter.optimize_goto_if_not(block)

def test_residual_call():
    for with_i in [False, True]:
        for with_r in [False, True]:
            for with_f in [False, True]:
                args = []
                if with_i: args += [lltype.Signed, lltype.Char]
                if with_r: args += [rclass.OBJECTPTR, lltype.Ptr(rstr.STR)]
                if with_f: args += [lltype.Float, lltype.Float]
                random.shuffle(args)
                if with_f: expectedkind = 'irf'    # all kinds
                elif with_i: expectedkind = 'ir'   # integers and references
                else: expectedkind = 'r'           # only references
                yield residual_call_test, args, expectedkind

def residual_call_test(argtypes, expectedkind):
    FUNC = lltype.FuncType(argtypes, lltype.Signed)
    fnptr = lltype.functionptr(FUNC, "g")    # no graph
    c_fnptr = Constant(fnptr, concretetype=lltype.typeOf(fnptr))
    vars = [varoftype(TYPE) for TYPE in argtypes]
    op = SpaceOperation('direct_call', [c_fnptr] + vars,
                        varoftype(lltype.Signed))
    op1 = jitter.rewrite_operation(op)
    assert op1.opname == 'residual_call_' + expectedkind
    assert op1.args[0] == c_fnptr
    assert len(op1.args) == 1 + len(expectedkind)
    for sublist, kind in zip(op1.args[1:], expectedkind):
        assert sublist == [v for v in vars
                             if getkind(v.concretetype).startswith(kind)]
