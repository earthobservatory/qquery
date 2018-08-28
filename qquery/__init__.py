__version__     = "0.0.1"
__url__         = "http://gitlab.jpl.nasa.gov:8000/browser/trunk/HySDS/hysds"
__description__ = "QQuery a generic product querying framework"

try:
    import scihub.scihub_query
except ImportError as e:
    pass
