Webcrawler Documentation
========================

This documentation explains the current crawler proof of concept from the point
of view of a new developer. The project is a public-source energy intelligence
pipeline: it discovers approved public URLs, fetches permitted content, extracts
readable text, cleans and redacts it, extracts claims, scores trust, stores
auditable records, and serves API/UI outputs.

Start with the architecture guide if you are new to the codebase. Use the API
reference when you need exact function, class, argument, return, and helper
details.

.. toctree::
   :maxdepth: 2
   :caption: Guides

   architecture
   deployment
   documentation_policy
   technical_debt

.. toctree::
   :maxdepth: 2
   :caption: Reference

   api

Build The Docs
--------------

From the repository root:

.. code-block:: powershell

   python -m pip install -e ".[dev]"
   python -m sphinx -b html docs docs/_build/html

Open ``docs/_build/html/index.html`` in a browser to read the rendered output.
