Documentation Policy
====================

Docstring Style
---------------

Use Google-style Python docstrings for all new and changed Python code. Sphinx
renders these through the ``sphinx.ext.napoleon`` extension.

Every module, class, public function, private helper, nested route handler, and
special method should explain:

- what it does;
- why the function or class exists in the pipeline;
- every argument and its expected meaning;
- the return value and how the caller uses it;
- every exception intentionally raised by the function.

Tone
----

Write for a junior developer who is new to crawling and intelligence pipelines.
Prefer concrete context over terse labels. A good docstring does not just say
"normalizes text"; it explains that normalized text lets later stages compare
evidence consistently and avoid storing page chrome as claims.

Sphinx Export Rules
-------------------

When adding a Python module:

1. Add Google-style docstrings to the module and all members.
2. Add the module to ``docs/api.rst``.
3. Run:

   .. code-block:: powershell

      python -m sphinx -b html docs docs/_build/html

4. Update ``docs/technical_debt.md`` if the module introduces or resolves known
   debt.

Definition Of Done
------------------

A code milestone is not complete until its docstrings render in Sphinx and the
API reference includes the new or changed module.
