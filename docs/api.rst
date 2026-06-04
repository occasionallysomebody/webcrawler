API Reference
=============

The reference below is generated from Python docstrings with Sphinx autodoc.
Private helpers are included on purpose. In this project, private helpers often
encode important audit, normalization, or compliance behavior that a maintainer
must understand when debugging a run.

Package
-------

.. automodule:: crawler

API Service
-----------

.. automodule:: crawler.api
   :members: create_app, app, _make_auth_dependency, _raise_auth_error, _run_dir, _read_json, _map_data_payload, _evidence_export_payload, _filter_map_records

Audit
-----

.. automodule:: crawler.audit

Configuration
-------------

.. automodule:: crawler.config

Corroboration
-------------

.. automodule:: crawler.corroboration

Incremental Crawls
------------------

.. automodule:: crawler.incremental

Cleaning
--------

.. automodule:: crawler.clean

Discovery
---------

.. automodule:: crawler.discovery

Extraction
----------

.. automodule:: crawler.extract

Fetching
--------

.. automodule:: crawler.fetch

Map UI
------

.. automodule:: crawler.map_ui

Models
------

.. automodule:: crawler.models

Onboarding
----------

.. automodule:: crawler.onboarding

Redaction
---------

.. automodule:: crawler.redact

Reporting
---------

.. automodule:: crawler.reporting

Robots And Access
-----------------

.. automodule:: crawler.robots

Runner
------

.. automodule:: crawler.runner

Signals
-------

.. automodule:: crawler.signals

Source Health
-------------

.. automodule:: crawler.source_health

Source Registry
---------------

.. automodule:: crawler.source_registry

Storage
-------

.. automodule:: crawler.storage

Trust Scoring
-------------

.. automodule:: crawler.trust
