from .decorator import decorator


@decorator
def synchronized(f, node, *args, **kw):
    """ Synchronization decorator """
    with node._lock:
        return f(node, *args, **kw)


class SynchronizedType(type):

    def __new__(cls, clsname, bases, local):
        for name, item in local.items():
            if callable(item) and not name.startswith("_"):
                local[name] = synchronized(item)
        return type.__new__(cls, clsname, bases, local)
