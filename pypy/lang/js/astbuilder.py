from pypy.rlib.rarithmetic import intmask, ovfcheck, ovfcheck_float_to_int
from pypy.rlib.parsing.tree import RPythonVisitor, Symbol, Nonterminal
from pypy.lang.js import operations
from pypy.rlib.parsing.parsing import ParseError

class FakeParseError(Exception):
    def __init__(self, pos, msg):
        self.pos = pos
        self.msg = msg

class ASTBuilder(RPythonVisitor):
    BINOP_TO_CLS = {
        '+': operations.Plus,
        '-': operations.Sub,
        '*': operations.Mult,
        '/': operations.Division,
        '%': operations.Mod,
        '^': operations.BitwiseXor,
        '|': operations.BitwiseOr,
        '&': operations.BitwiseAnd,
        '&&': operations.And,
        '||': operations.Or,
        '==': operations.Eq,
        '!=': operations.Ne,
        '!==': operations.StrictNe,
        '===': operations.StrictEq,
        '>': operations.Gt,
        '>=': operations.Ge,
        '<': operations.Lt,
        '<=': operations.Le,
        '>>': operations.Rsh,
        '>>>': operations.Ursh,
        '<<': operations.Lsh,
        '.': operations.MemberDot,
        '[': operations.Member,
        ',': operations.Comma,
        'in': operations.In,
    }
    UNOP_TO_CLS = {
        '~': operations.BitwiseNot,
        '!': operations.Not,
        '+': operations.UPlus,
        '-': operations.UMinus,
        'typeof': operations.Typeof,
        'void': operations.Void,
        'delete': operations.Delete,
    }
    LISTOP_TO_CLS = {
        '[': operations.Array,
        '{': operations.ObjectInit,
    }
    
    def __init__(self):
        self.varlists = []
        self.funclists = []
        self.sourcename = ""
        RPythonVisitor.__init__(self)
    
    def set_sourcename(self, sourcename):
        self.sourcename = sourcename #XXX I should call this
    
    def get_pos(self, node):
        value = ''
        source_pos = None
        if isinstance(node, Symbol):
            value = node.additional_info
            source_pos = node.token.source_pos
        elif len(node.children) > 0:
            curr = node.children[0]
            while not isinstance(curr, Symbol):
                if len(curr.children):
                    curr = curr.children[0]
                else:
                    break
            else:
                value = curr.additional_info
                source_pos = curr.token.source_pos

        # XXX some of the source positions are not perfect
        if source_pos is None:
            return operations.Position()
        return operations.Position(
                   source_pos.lineno,
                   source_pos.columnno,
                   source_pos.columnno + len(value))

    def visit_DECIMALLITERAL(self, node):
        pos = self.get_pos(node)
        try:
            
            f = float(node.additional_info)
            i = ovfcheck_float_to_int(f)
            if i != f:
                return operations.FloatNumber(pos, f)
            else:
                return operations.IntNumber(pos, i)
        except (ValueError, OverflowError):
            return operations.FloatNumber(pos, float(node.additional_info))
    
    def visit_HEXINTEGERLITERAL(self, node):
        pos = self.get_pos(node)
        return operations.IntNumber(pos, int(node.additional_info, 16))

    def visit_OCTALLITERAL(self, node):
        pos = self.get_pos(node)
        return operations.IntNumber(pos, int(node.additional_info, 8))

    def string(self,node):
        pos = self.get_pos(node)
        return operations.String(pos, node.additional_info)
    visit_DOUBLESTRING = string
    visit_SINGLESTRING = string

    def binaryop(self, node):
        left = self.dispatch(node.children[0])
        for i in range((len(node.children) - 1) // 2):
            op = node.children[i * 2 + 1]
            pos = self.get_pos(op)
            right = self.dispatch(node.children[i * 2 + 2])
            result = self.BINOP_TO_CLS[op.additional_info](pos, left, right)
            left = result
        return left
    visit_additiveexpression = binaryop
    visit_multiplicativeexpression = binaryop
    visit_bitwisexorexpression = binaryop
    visit_bitwiseandexpression = binaryop
    visit_bitwiseorexpression = binaryop
    visit_equalityexpression = binaryop
    visit_logicalorexpression = binaryop
    visit_logicalandexpression = binaryop
    visit_relationalexpression = binaryop
    visit_shiftexpression = binaryop
    visit_expression = binaryop
    visit_expressionnoin = binaryop
    
    def visit_memberexpression(self, node):
        if isinstance(node.children[0], Symbol) and \
           node.children[0].additional_info == 'new': # XXX could be a identifier?
            pos = self.get_pos(node)
            left = self.dispatch(node.children[1])
            right = self.dispatch(node.children[2])
            return operations.NewWithArgs(pos, left, right)
        else:
            return self.binaryop(node)


    def literalop(self, node):
        pos = self.get_pos(node);
        value = node.children[0].additional_info
        if value == "true":
            return operations.Boolean(pos, True)
        elif value == "false":
            return operations.Boolean(pos, False)
        else:
            return operations.Null(pos)
    visit_nullliteral = literalop
    visit_booleanliteral = literalop

    def visit_unaryexpression(self, node):
        op = node.children[0]
        pos = self.get_pos(op)
        child = self.dispatch(node.children[1])
        if op.additional_info in ['++', '--']:
            return self._dispatch_assignment(pos, child, op.additional_info,
                                             'pre')
        return self.UNOP_TO_CLS[op.additional_info](pos, child)

    def _dispatch_assignment(self, pos, left, atype, prepost):
        from pypy.lang.js.operations import Identifier, Member, MemberDot,\
             VariableIdentifier

        if isinstance(left, Identifier):
            return operations.SimpleAssignment(pos, left, None, atype, prepost)
        elif isinstance(left, VariableIdentifier):
            # XXX exchange to VariableAssignment
            return operations.SimpleAssignment(pos, left, None, atype,
                                                 prepost)
        elif isinstance(left, Member):
            return operations.MemberAssignment(pos, left.left, left.expr,
                                               None, atype, prepost)
        elif isinstance(left, MemberDot):
            return operations.MemberDotAssignment(pos, left.left, left.name,
                                                  None, atype, prepost)
        else:
            return operations.SimpleIncrement(pos, left, atype)

    def visit_postfixexpression(self, node):
        op = node.children[1]
        pos = self.get_pos(op)
        child = self.dispatch(node.children[0])
        # all postfix expressions are assignments
        return self._dispatch_assignment(pos, child, op.additional_info, 'post')
    
    def listop(self, node):
        op = node.children[0]
        pos = self.get_pos(op)
        l = [self.dispatch(child) for child in node.children[1:]]
        return self.LISTOP_TO_CLS[op.additional_info](pos, l)
    visit_arrayliteral = listop # elision
    visit_objectliteral = listop

    def visit_block(self, node):
        op = node.children[0]
        pos = self.get_pos(op)
        l = [self.dispatch(child) for child in node.children[1:]]
        return operations.Block(pos, l)

    def visit_arguments(self, node):
        pos = self.get_pos(node)
        nodes = [self.dispatch(child) for child in node.children[1:]]
        return operations.ArgumentList(pos, nodes)
    
    def visit_formalparameterlist(self, node):
        pos = self.get_pos(node)
        nodes = [self.dispatch(child) for child in node.children]
        return operations.ArgumentList(pos, nodes)
    
    def visit_variabledeclarationlist(self, node):
        pos = self.get_pos(node)
        nodes = [self.dispatch(child) for child in node.children]
        return operations.VariableDeclList(pos, nodes)
    visit_variabledeclarationlistnoin = visit_variabledeclarationlist
    
    def visit_propertynameandvalue(self, node):
        pos = self.get_pos(node)
        l = node.children[0]
        if l.symbol == "IDENTIFIERNAME":
            lpos = self.get_pos(l)
            left = operations.Identifier(lpos, l.additional_info)
        else:
            left = self.dispatch(l)
        right = self.dispatch(node.children[1])
        return operations.PropertyInit(pos,left,right)

    def _search_identifier(self, name):
        lenall = len(self.varlists)
        for i in range(lenall):
            num = lenall - i - 1
            vardecl = self.varlists[num]
            if name in vardecl:
                return i, vardecl
        raise ValueError("xxx")
    
    def visit_IDENTIFIERNAME(self, node):
        pos = self.get_pos(node)
        name = node.additional_info
        try:
            t = self._search_identifier(name)
        except ValueError:
            pass
        else:
            i, vardecl = t
            return operations.VariableIdentifier(pos, i, name)
        return operations.Identifier(pos, name)
    
    def visit_program(self, node):
        pos = self.get_pos(node)
        body = self.dispatch(node.children[0])
        return operations.Program(pos, body)
    
    def visit_variablestatement(self, node):
        pos = self.get_pos(node)
        body = self.dispatch(node.children[0])
        return operations.Variable(pos, body)

    def visit_throwstatement(self, node):
        pos = self.get_pos(node)
        exp = self.dispatch(node.children[0])
        return operations.Throw(pos, exp)
        
    def visit_sourceelements(self, node):
        pos = self.get_pos(node)
        self.varlists.append({})
        self.funclists.append({})
        nodes=[]
        for child in node.children:
            node = self.dispatch(child)
            if node is not None:
                nodes.append(node)
        var_decl = self.varlists.pop().keys()
        func_decl = self.funclists.pop()
        return operations.SourceElements(pos, var_decl, func_decl, nodes, self.sourcename)
    
    def functioncommon(self, node, declaration=True):
        pos = self.get_pos(node)
        i=0
        identifier, i = self.get_next_expr(node, i)
        parameters, i = self.get_next_expr(node, i)
        functionbody, i = self.get_next_expr(node, i)
        if parameters is None:
            p = []
        else:
            p = [pident.get_literal() for pident in parameters.nodes]
        funcobj = operations.FunctionStatement(pos, identifier, p, functionbody)
        if declaration:
            self.funclists[-1][identifier.get_literal()] = funcobj
        return funcobj
    
    def visit_functiondeclaration(self, node):
        self.functioncommon(node)
        return None
    
    def visit_functionexpression(self, node):
        return self.functioncommon(node, declaration=False)
    
    def visit_variabledeclaration(self, node):
        pos = self.get_pos(node)
        identifier = self.dispatch(node.children[0])
        self.varlists[-1][identifier.get_literal()] = None
        if len(node.children) > 1:
            expr = self.dispatch(node.children[1])
        else:
            expr = None
        return operations.VariableDeclaration(pos, identifier, expr)
    visit_variabledeclarationnoin = visit_variabledeclaration
    
    def visit_expressionstatement(self, node):
        pos = self.get_pos(node)
        return operations.ExprStatement(pos, self.dispatch(node.children[0]))
    
    def visit_callexpression(self, node):
        pos = self.get_pos(node)
        left = self.dispatch(node.children[0])
        nodelist = node.children[1:]
        while nodelist:
            currnode = nodelist.pop(0)
            if isinstance(currnode, Symbol):
                op = currnode
                right = self.dispatch(nodelist.pop(0))
                left = self.BINOP_TO_CLS[op.additional_info](pos, left, right)
            else:
                right = self.dispatch(currnode)
                left = operations.Call(pos, left, right)
        
        return left
        
    def visit_assignmentexpression(self, node):
        from pypy.lang.js.operations import Identifier, Member, MemberDot,\
             VariableIdentifier
        pos = self.get_pos(node)
        left = self.dispatch(node.children[0])
        atype = node.children[1].additional_info
        right = self.dispatch(node.children[2])
        if isinstance(left, Identifier):
            return operations.SimpleAssignment(pos, left, right, atype)
        elif isinstance(left, VariableIdentifier):
            # XXX exchange to VariableAssignment
            return operations.SimpleAssignment(pos, left, right, atype)
        elif isinstance(left, Member):
            return operations.MemberAssignment(pos, left.left, left.expr,
                                               right, atype)
        elif isinstance(left, MemberDot):
            return operations.MemberDotAssignment(pos, left.left, left.name,
                                                  right, atype)
        else:
            raise FakeParseError(pos, "invalid lefthand expression")
    visit_assignmentexpressionnoin = visit_assignmentexpression
        
    def visit_emptystatement(self, node):
        pos = self.get_pos(node)
        return operations.Empty(pos)
    
    def visit_newexpression(self, node):
        if len(node.children) == 1:
            return self.dispatch(node.children[0])
        else:
            pos = self.get_pos(node)
            val = self.dispatch(node.children[1])
            return operations.New(pos, val)
    
    def visit_ifstatement(self, node):
        pos = self.get_pos(node)
        condition = self.dispatch(node.children[0])
        ifblock =  self.dispatch(node.children[1])
        if len(node.children) > 2:
            elseblock =  self.dispatch(node.children[2])
        else:
            elseblock = None
        return operations.If(pos, condition, ifblock, elseblock)
    
    def visit_iterationstatement(self, node):
        return self.dispatch(node.children[0])
    
    def visit_whiles(self, node):
        pos = self.get_pos(node)
        itertype = node.children[0].additional_info
        if itertype == 'while':
            condition = self.dispatch(node.children[1])
            block = self.dispatch(node.children[2])
            return operations.While(pos, condition, block)
        elif itertype == "do":
            condition = self.dispatch(node.children[2])
            block = self.dispatch(node.children[1])
            return operations.Do(pos, condition, block)
        else:
            raise NotImplementedError("Unknown while version %s" % (itertype,))
    
    def visit_regularfor(self, node):
        pos = self.get_pos(node)
        i = 1
        setup, i = self.get_next_expr(node, i)
        condition, i = self.get_next_expr(node, i)
        if isinstance(condition, operations.Undefined):
            condition = operations.Boolean(pos, True)
        update, i = self.get_next_expr(node, i)
        body, i = self.get_next_expr(node, i)
        return operations.For(pos, setup, condition, update, body)
    visit_regularvarfor = visit_regularfor
    
    def visit_infor(self, node):
        from pypy.lang.js.operations import Identifier
        pos = self.get_pos(node)
        left = self.dispatch(node.children[1])
        right = self.dispatch(node.children[2])
        body= self.dispatch(node.children[3])
        assert isinstance(left, Identifier)
        return operations.ForIn(pos, left.name, right, body)
    
    def visit_invarfor(self, node):
        pos = self.get_pos(node)
        left = self.dispatch(node.children[1])
        right = self.dispatch(node.children[2])
        body= self.dispatch(node.children[3])
        return operations.ForVarIn(pos, left, right, body)    
    
    def get_next_expr(self, node, i):
        if isinstance(node.children[i], Symbol) and \
           node.children[i].additional_info in [';', ')', '(', '}']:
            return None, i+1
        else:
            return self.dispatch(node.children[i]), i+2
    
    def visit_breakstatement(self, node):
        pos = self.get_pos(node)
        if len(node.children) > 0:
            target = self.dispatch(node.children[0])
        else:
            target = None
        return operations.Break(pos, target)
    
    def visit_continuestatement(self, node):
        pos = self.get_pos(node)
        if len(node.children) > 0:
            target = self.dispatch(node.children[0])
        else:
            target = None
        return operations.Continue(pos, target)
    
    def visit_returnstatement(self, node):
        pos = self.get_pos(node)
        if len(node.children) > 0:
            value = self.dispatch(node.children[0])
        else:
            value = None
        return operations.Return(pos, value)

    def visit_conditionalexpression(self, node):
        pos = self.get_pos(node)
        condition = self.dispatch(node.children[0])
        truepart = self.dispatch(node.children[2])
        falsepart = self.dispatch(node.children[3])
        return operations.If(pos, condition, truepart, falsepart)
    
    def visit_trystatement(self, node):
        pos = self.get_pos(node)
        tryblock = self.dispatch(node.children[0])
        catchparam = None
        catchblock = None
        finallyblock = None
        if node.children[1].children[0].additional_info == "catch":
            catchparam = self.dispatch(node.children[1].children[1])
            catchblock = self.dispatch(node.children[1].children[2])
            if len(node.children) > 2:
                finallyblock = self.dispatch(node.children[2].children[1])
        else:
            finallyblock = self.dispatch(node.children[1].children[1])
        return operations.Try(pos, tryblock, catchparam, catchblock, finallyblock)
    
    def visit_primaryexpression(self, node):
        pos = self.get_pos(node)
        return operations.This(pos, 'this')
    
    def visit_withstatement(self, node):
        pos = self.get_pos(node)
        identifier = self.dispatch(node.children[0])
        body = self.dispatch(node.children[1])
        return operations.With(pos, identifier, body)
        
