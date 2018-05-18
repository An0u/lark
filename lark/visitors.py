from inspect import isclass, getmembers, getmro
from functools import wraps

from .utils import smart_decorator
from .tree import Tree

class Discard(Exception):
    pass


# Transformers

class Transformer:
    def _call_userfunc(self, data, children, meta):
        # Assumes tree is already transformed
        try:
            f = getattr(self, data)
        except AttributeError:
            return self.__default__(data, children, meta)
        else:
            if getattr(f, 'meta', False):
                return f(children, meta)
            elif getattr(f, 'inline', False):
                return f(*children)
            else:
                return f(children)

    def _transform_children(self, children):
        for c in children:
            try:
                yield self._transform_tree(c) if isinstance(c, Tree) else c
            except Discard:
                pass

    def _transform_tree(self, tree):
        children = list(self._transform_children(tree.children))
        return self._call_userfunc(tree.data, children, tree.meta)

    def transform(self, tree):
        return self._transform_tree(tree)

    def __mul__(self, other):
        return TransformerChain(self, other)

    def __default__(self, data, children, meta):
        "Default operation on tree (for override)"
        return Tree(data, children, meta)

    @classmethod
    def _apply_decorator(cls, decorator, **kwargs):
        mro = getmro(cls)
        assert mro[0] is cls
        libmembers = {name for _cls in mro[1:] for name, _ in getmembers(_cls)}
        for name, value in getmembers(cls):
            if name.startswith('_') or name in libmembers:
                continue

            setattr(cls, name, decorator(value, **kwargs))
        return cls


class InlineTransformer(Transformer):   # XXX Deprecated
    def _call_userfunc(self, data, children, meta):
        # Assumes tree is already transformed
        try:
            f = getattr(self, data)
        except AttributeError:
            return self.__default__(data, children, meta)
        else:
            return f(*children)


class TransformerChain(object):
    def __init__(self, *transformers):
        self.transformers = transformers

    def transform(self, tree):
        for t in self.transformers:
            tree = t.transform(tree)
        return tree

    def __mul__(self, other):
        return TransformerChain(*self.transformers + (other,))


class Transformer_InPlace(Transformer):
    def _transform_tree(self, tree):           # Cancel recursion
        return self._call_userfunc(tree.data, tree.children, tree.meta)

    def transform(self, tree):
        for subtree in tree.iter_subtrees():
            subtree.children = list(self._transform_children(subtree.children))

        return self._transform_tree(tree)


class Transformer_InPlaceRecursive(Transformer):
    def _transform_tree(self, tree):
        tree.children = list(self._transform_children(tree.children))
        return self._call_userfunc(tree.data, tree.children, tree.meta)



# Visitors

class VisitorBase:
    def _call_userfunc(self, tree):
        return getattr(self, tree.data, self.__default__)(tree)

    def __default__(self, tree):
        "Default operation on tree (for override)"
        return tree


class Visitor(VisitorBase):
    "Bottom-up visitor"

    def visit(self, tree):
        for subtree in tree.iter_subtrees():
            self._call_userfunc(subtree)
        return tree

class Visitor_Recursive(VisitorBase):
    def visit(self, tree):
        for child in tree.children:
            if isinstance(child, Tree):
                self.visit(child)

        f = getattr(self, tree.data, self.__default__)
        f(tree)
        return tree



def visit_children_decor(func):
    @wraps(func)
    def inner(cls, tree):
        values = cls.visit_children(tree)
        return func(cls, values)
    return inner


class Interpreter:
    "Top-down visitor"

    def visit(self, tree):
        return getattr(self, tree.data)(tree)

    def visit_children(self, tree):
        return [self.visit(child) if isinstance(child, Tree) else child
                for child in tree.children]

    def __getattr__(self, name):
        return self.__default__

    def __default__(self, tree):
        return self.visit_children(tree)




# Decorators

def _apply_decorator(obj, decorator, **kwargs):
    try:
        _apply = obj._apply_decorator
    except AttributeError:
        return decorator(obj, **kwargs)
    else:
        return _apply(decorator, **kwargs)



def _inline_args__func(func):
    @wraps(func)
    def create_decorator(_f, with_self):
        if with_self:
            def f(self, children):
                return _f(self, *children)
        else:
            def f(self, children):
                return _f(*children)
        return f

    return smart_decorator(func, create_decorator)


def inline_args(obj):   # XXX Deprecated
    return _apply_decorator(obj, _inline_args__func)



def _visitor_args_func_dec(func, inline=False, meta=False):
    assert not (inline and meta)
    def create_decorator(_f, with_self):
        if with_self:
            def f(self, *args, **kwargs):
                return _f(self, *args, **kwargs)
        else:
            def f(self, *args, **kwargs):
                return _f(*args, **kwargs)
        return f

    f = smart_decorator(func, create_decorator)
    f.inline = inline
    f.meta = meta
    return f

def visitor_args(inline=False, meta=False):
    if inline and meta:
        raise ValueError("Visitor functions can either accept meta, or be inlined. Not both.")
    def _visitor_args_dec(obj):
        return _apply_decorator(obj, _visitor_args_func_dec, inline=inline, meta=meta)
    return _visitor_args_dec


