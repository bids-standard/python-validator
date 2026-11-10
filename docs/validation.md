# How python-validator checks a dataset

This describes the full validation layer: what each module is for, how one file is
checked from start to finish, which findings it can produce, how it compares with the
reference validator (bids-validator, written in TypeScript and run with Deno), and every
place where the two differ on purpose.

It covers filename and folder checks, file-integrity checks, and every rule the BIDS
schema writes with selectors: `rules.checks`, the JSON field rules (`rules.sidecars`,
`rules.json`, `rules.dataset_metadata`) and the table rules (`rules.tabular_data`). Rules
that need associated files (the link from a scan to its events file, issue #82), HED, and
OME/TIFF metadata are held back; section 9 lists them.

Contents:

1. [The layout](#1-the-layout)
2. [One file, start to finish](#2-one-file-start-to-finish)
3. [Findings and where their codes come from](#3-findings-and-where-their-codes-come-from)
4. [Which files and folders are visited](#4-which-files-and-folders-are-visited)
5. [Names and places](#5-names-and-places)
6. [Reading files](#6-reading-files)
7. [The schema's rules](#7-the-schemas-rules)
8. [Changes to the expression language and the context](#8-changes-to-the-expression-language-and-the-context)
9. [Comparison with the reference validator](#9-comparison-with-the-reference-validator)
10. [Defects found in other projects](#10-defects-found-in-other-projects)
11. [Adding a check](#11-adding-a-check)
12. [Tests](#12-tests)
13. [Module reference](#13-module-reference)

---

## 1. The layout

The code is grouped by HOW a check works, not by what it looks at. Names and places are
checked against lookup tables (`rules.files`, `rules.directories`); everything else the
schema says about a file is a rule with selectors, run by one engine that hands each
rule's payload to the module that knows it. That is the reference validator's own
structure (`applyRules.ts`).

Everything that turns a dataset into findings is one package, `bids_validator/checks/`.
What it builds on stays where upstream has it, beside the package:

```text
src/bids_validator/
    __main__.py              the command line
    issues.py                what a finding is
    context.py               what is known about one file (upstream)
    expression_language.py   what a schema expression evaluates to (upstream)
    bids_validator.py, bidsignore.py, types/   (upstream)
    checks/                  the validation layer
        __init__.py          collect_issues: which checks run, in what order
        walk.py              which files and folders are visited
        integrity.py  inheritance.py  filenames.py  filename_rules.py
        rules.py  expressions.py  fields.py  tables.py  values.py  schema_cache.py
```

| Module (under `src/bids_validator/`) | Question it answers | Reference (bids-validator) |
|---|---|---|
| `checks/__init__.py` | Which checks run, in what order? | `validators/bids.ts` |
| `checks/walk.py` | Which files and folders are visited? | `schema/walk.ts`, `files/ignore.ts`, `validators/bids.ts` |
| `checks/integrity.py` | Can the file be read at all? | `validators/internal/emptyFile.ts`, the loaders in `files/` |
| `checks/inheritance.py` | Does a deeper JSON file change a value set above it? | `loadSidecar` in `schema/context.ts` |
| `checks/filenames.py` | Is the name, and the place, legal? | `validators/filenameValidate.ts`, `filenameCase.ts`, `findDirRuleMatches` |
| `checks/filename_rules.py` | Which `rules.files` rules describe this file's name? | `validators/filenameIdentify.ts` |
| `checks/rules.py` | Which schema rules apply to the file? Hands each payload to its module; reports nothing itself. | `schema/applyRules.ts` |
| `checks/expressions.py` | Payload `checks`: are the rule's expressions true? | `evalRuleChecks` in `applyRules.ts` |
| `checks/fields.py` | Payload `fields`: are the JSON fields there, with valid values? | `evalJsonCheck` in `applyRules.ts` |
| `checks/tables.py` | Payloads `columns`, `initial_columns`, `index_columns` | `schema/tables.ts` |
| `checks/values.py` | Does one value satisfy its schema definition? | `validators/json.ts` (ajv) |
| `checks/schema_cache.py` | Work something out from the schema once, not for every file | (the reference loads its schema into plain objects once) |
| `issues.py` | What is a finding? (data only: no file, no schema) | `types/issues.ts`, `issues/datasetIssues.ts` |
| `context.py` | What is known about one file? (upstream) | `schema/context.ts` |
| `expression_language.py` | What does a schema expression evaluate to? (upstream) | `schema/expressionLanguage.ts` |

The tests mirror the layout: the tests of `checks/<module>.py` are in
`tests/checks/test_<module>.py`, and `tests/checks/test_collect_issues.py` tests the
package's `collect_issues`.

```mermaid
flowchart TD
    CLI["__main__.py: the command line"] --> CHECKS["checks/__init__.py: the order and the loop"]
    CHECKS --> WALK["checks/walk.py: which files"]
    CHECKS --> INT["checks/integrity.py"]
    CHECKS --> INHERIT["checks/inheritance.py"]
    CHECKS --> FN["checks/filenames.py"]
    CHECKS --> RE["checks/rules.py"]
    FN --> FR["checks/filename_rules.py: which filename rules"]
    RE --> FR
    RE --> EC["checks/expressions.py: payload checks"]
    RE --> FC["checks/fields.py: payload fields"]
    RE --> TC["checks/tables.py: payload columns"]
    EC --> EL["expression_language.py"]
    FC --> VAL["checks/values.py"]
    INHERIT --> VAL
    INT --> CTX["context.py"]
    WALK --> CTX
    EL --> CTX
```

Each check module lists the codes it reports at its top (section 3) and builds its
findings from them; `issues.py` only says what a finding is. Files are read only through
`context.py`. No check module imports another check module's checks: the two that both
need a file's filename rules get them from `checks/filename_rules.py`, and the rule
engine only imports the payload handlers it dispatches to.

## 2. One file, start to finish

`checks.collect_issues(tree, schema)` runs the dataset checks once, then walks the
dataset and gives every visited folder to the folder checks and every visited file to
the file checks, in this order:

```python
DATASET_CHECKS = (dataset_integrity_issues,)
FOLDER_CHECKS = (folder_issues,)
FILE_CHECKS = (integrity_issues, inheritance_issues, filename_issues, rule_issues)
```

That is the reference validator's order: problems reading a file first (its context
loaders report them), then the name, then the schema rules. A directory recording
(`sub-01_task-x_meg.ds/`) is a folder on disk but a file to BIDS, so it gets the file
checks; a file check never has to ask whether it was given a folder.

```mermaid
flowchart TD
    W["checks/walk.py yields a Context"] --> D{"a plain folder?"}
    D -- yes --> FOLDER["folder_issues: rules.directories"]
    D -- no --> I["integrity_issues: empty? JSON parses? header readable? table shape?"]
    I --> H["inheritance_issues: does a deeper sidecar change a value?"]
    H --> F["filename_issues: matching_filename_rules, then hold the name to them; letter case"]
    F --> R["rule_issues: hide_unused_name_parts, then every rule whose selectors all hold"]
    R --> P1["checks payload: checks.expressions"]
    R --> P2["fields payload: checks.fields"]
    R --> P3["columns payloads: checks.tables"]
```

A file's `Context` is built once and shared by every check, so whatever it loads (the
merged sidecar, the NIfTI header, the table) is loaded once. The dataset is walked once,
and the JSON files a file inherits from are found once per file
(`Context.sidecar_files`), however many checks need them.

From Python:

```python
from bidsschematools.schema import load_schema
from bids_validator.checks import collect_issues
from bids_validator.types.files import FileTree

issues = collect_issues(FileTree.read_from_filesystem('my_dataset'), load_schema())
for issue in issues:
    print(issue.severity.value, issue.code, issue.location, issue.rule)
```

`collect_issues(..., dataset_checks=(), folder_checks=(), file_checks=(filename_issues,))`
runs one check alone.

From the command line (`bids-validator my_dataset`), on a small dataset with a few
deliberate problems (recommended-field warnings left out):

```console
warning: README_FILE_SMALL: README
    The recommended file '/README' is very small. Please consider expanding it ...
warning: TOO_FEW_AUTHORS: dataset_description.json
    The 'Authors' field of 'dataset_description.json' should contain an array of ...
error: TSV_VALUE_INCORRECT_TYPE: participants.tsv
    line 2: 'thirty'
error: T1W_FILE_WITH_TOO_MANY_DIMENSIONS: sub-01/anat/sub-01_T1w.nii.gz
    _T1w.nii[.gz] files must have exactly three dimensions.
error: EMPTY_FILE: sub-01/func/sub-01_task-rest_bold.nii.gz
    Empty files not allowed.
error: NIFTI_HEADER_UNREADABLE: sub-01/func/sub-01_task-rest_bold.nii.gz
    We were unable to parse header data from this NIfTI file. ...
error: SIDECAR_KEY_REQUIRED: sub-01/func/sub-01_task-rest_bold.nii.gz
    the required field 'TaskName' is missing
error: JSON_SCHEMA_VALIDATION_ERROR: sub-01/func/sub-01_task-rest_bold.json
    RepetitionTime must be > 0

6 error(s), 61 warning(s)
```

The reference validator reports the same findings on this dataset, except one
`JSON_KEY_RECOMMENDED` (section 9.3, item 2). The exit code is 1 when there is an
error, 0 otherwise; `-v` adds the schema rule of each finding.

## 3. Findings and where their codes come from

`issues.py` is the data model and nothing else: it reads no file and no schema.

* `IssueDefinition(code, severity, reason)` is a KIND of finding, such as `EMPTY_FILE`.
* `Issue` is one finding: `code`, `severity` (`error` or `warning`), `location` (the
  dataset-relative path, without a leading `/`; `None` for the dataset as a whole),
  `message`, `sub_code` (a field, column or entity name) and `rule` (the schema rule's
  dotted path). `definition.make_issue(location, message=..., sub_code=..., rule=...)`
  makes one; the message defaults to the definition's `reason`.
* `DatasetIssues` holds every finding of one run, in order.

A code is defined in exactly one place, and that place is decided by whether the schema
defines it:

* **The schema defines it**, so it is READ from the schema where it is reported:
  `IssueDefinition.from_schema(block)` turns the schema's `{code, level, message}` into a
  definition. That covers the `issue` of every `rules.checks` rule, the `issue` some
  fields carry (`NO_AUTHORS`, `B0_FIELD_IDENTIFIER_RECOMMENDED` ...), and six entries of
  `rules.errors`: `NotIncluded`, `EmptyFile`, `NiftiHeaderUnreadable`, `JsonInvalid`,
  `InvalidJsonEncoding`, `JsonSchemaValidationError`.
* **Only the reference validator defines it** (bids-validator `src/issues/list.ts`), so
  it is WRITTEN OUT, once, at the top of the module that reports it:

| Module | Codes it writes out |
|---|---|
| `checks.filenames` | `ENTITY_WITH_NO_LABEL`, `INVALID_ENTITY_LABEL`, `MISSING_REQUIRED_ENTITY`, `ENTITY_NOT_IN_RULE`, `MISSING_DATATYPE`, `DATATYPE_MISMATCH`, `EXTENSION_MISMATCH`, `INVALID_LOCATION`, `FILENAME_MISMATCH`, `ALL_FILENAME_RULES_HAVE_ISSUES`, `CASE_COLLISION` |
| `checks.integrity` | `MISSING_DATASET_DESCRIPTION`, and what the context's loaders raise: `JSON_NOT_AN_OBJECT`, `TSV_EMPTY_LINE`, `TSV_EQUAL_ROWS`, `TSV_COLUMN_HEADER_DUPLICATE`, `INVALID_GZIP`, `MULTIPLE_INHERITABLE_FILES` |
| `checks.inheritance` | `SIDECAR_FIELD_OVERRIDE` |
| `checks.expressions` | `CHECK_ERROR` |
| `checks.fields` | `SIDECAR_KEY_REQUIRED`, `SIDECAR_KEY_RECOMMENDED`, `JSON_KEY_REQUIRED`, `JSON_KEY_RECOMMENDED` |
| `checks.tables` | `TSV_COLUMN_MISSING`, `TSV_COLUMN_ORDER_INCORRECT`, `TSV_ADDITIONAL_COLUMNS_NOT_ALLOWED`, `TSV_ADDITIONAL_COLUMNS_MUST_DEFINE`, `TSV_ADDITIONAL_COLUMNS_UNDEFINED`, `TSV_COLUMN_TYPE_REDEFINED`, `TSV_VALUE_INCORRECT_TYPE`, `TSV_PSEUDO_AGE_DEPRECATED`, `TSV_INDEX_VALUE_NOT_UNIQUE` |

A check then reports a written-out code by name,
`MISSING_DATATYPE.make_issue(location, ...)`, so a typo is a `NameError` the linter
catches, not a wrong code at run time.

The context's loaders (`context.py`) raise a `ValidationError` carrying a code (they
cannot import the check modules). `checks.integrity.LOADER_ERRORS` and
`LOADER_ERRORS_IN_SCHEMA` say where each of those codes is defined.

The reference validator keeps all its codes in one list (`src/issues/list.ts`, which
also copies the six the schema defines). Here each list sits beside the checks that use
it, and `tests/checks/test_codes.py` keeps the one-place rule true: no code is written
out twice, no code the schema defines is written out at all, every definition is named
after its code, every `rules.errors` entry a module reads exists, and every code a
loader raises has a definition.

## 4. Which files and folders are visited

`checks.walk.iter_contexts(dataset)` yields a context for every file AND every folder
that is not ignored, each folder's files before its subfolders, as in the reference.

| What | Treatment |
|---|---|
| `/sourcedata/`, `/derivatives/`, `/code/`, `/stimuli/`, `/log/`, `/doc/` | ignored: the reference's default list, anchored at the dataset root (`DEFAULT_IGNORES`); a deeper `sub-01/log/` is checked |
| hidden files and folders (`.git`, `.DS_Store`, `.datalad`) | ignored at every level (`PRUNED`) |
| whatever `.bidsignore` lists | ignored; `.bidsignore` itself is visited and exempt from `NOT_INCLUDED` |
| a directory recording: entities, a suffix and an extension the schema spells with `/` (`.ds/`, `.mefd/`, `.ome.zarr/`, and a bare `/`) | visited as ONE file, not walked into |
| an opaque folder (`rules.directories`: `docs`, `logs` ...) | visited, not walked into |
| a `derivatives` folder in a raw dataset, at any depth | skipped: a separate dataset with separate rules |
| any other folder | visited, then walked into |

The bare `/` extension (`objects.extensions.Directory`) means a folder named like a file,
for example `sub-16/log/20200910-165242_99fc.../` in an fMRIPrep output, is one unit:
the reference reports it, and does not look inside.

`checks.walk.is_plain_folder(context)` tells a plain folder from a file or a recording.

## 5. Names and places

Nothing is opened to check a name.

`checks.filenames.folder_issues(context)`: a FOLDER must match a `rules.directories` rule
by exact name (`phenotype`), by entity (a name starting with `sub-` or `ses-`) or by value
(any datatype), as in the reference; otherwise it is `NOT_INCLUDED`. Like the reference,
the depth is not checked.

`checks.filenames.filename_issues(context)`: a FILE is first IDENTIFIED.
`checks.filename_rules.matching_filename_rules(context)` returns the `rules.files` rules
that describe it: those it matches by fixed path (`dataset_description.json`), by stem
glob (`participants`) or by suffix (derivative rules only in a derivative dataset),
narrowed to the best candidates (the rule for the file's folder first, then the rules
its entities and extension fit). The rules are read out of the schema once into plain
`checks.filename_rules.FilenameRule` values (entities already as short names, a list the
rule does not have as `None`) and indexed by path and suffix, so a file is compared with
a handful of rules rather than all 179. The name is then held to those rules:

| Code | When |
|---|---|
| `NOT_INCLUDED` | no rule matches |
| `ENTITY_WITH_NO_LABEL` | `acq-` (empty) or `foo` (no hyphen) in a name whose rule uses entities |
| `INVALID_ENTITY_LABEL` | a label breaks its entity's format (`acq-a!b`) |
| `MISSING_REQUIRED_ENTITY` | a required entity is missing (not checked for files at the root) |
| `ENTITY_NOT_IN_RULE` | an entity the rule does not allow |
| `MISSING_DATATYPE` | a data file in no datatype folder (`sub-01/sub-01_T1w.nii.gz`) |
| `DATATYPE_MISMATCH` | a data file in another datatype's folder |
| `EXTENSION_MISMATCH` | an extension the rule does not allow |
| `INVALID_LOCATION` | a valid name under the wrong `sub-`/`ses-` folders |
| `FILENAME_MISMATCH` | entities out of the schema's order or duplicated |
| `ALL_FILENAME_RULES_HAVE_ISSUES` | several rules match and none fits cleanly |
| `CASE_COLLISION` | another file in the folder differs only by letter case |

`MISSING_DATATYPE` and `DATATYPE_MISMATCH` never apply to `.json`, `.tsv`, `.bvec` and
`.bval` (`SIDECAR_EXTENSIONS`): those may sit above the data they describe. A sidecar lost
in a bogus folder (`sub-01/ses-1/foo/x.json`) is still caught, through the folder's own
`NOT_INCLUDED`. `MISSING_DATATYPE` is the reference's code since 2026-10-08 (commit
`f0cc83fb`, not yet in a release); before it, this case was reported as
`INVALID_LOCATION` here and missed by the reference.

`checks.filename_rules.hide_unused_name_parts(context, rules)` returns the context as
the schema's other rules see it once the name is identified: a name part that none of
the file's filename rules uses is hidden (the reference's `cleanContext`). A file that
matched no rule has no entities, suffix or extension for the rules to read, so
`.bidsignore` or an unrecognised file is not held to the sidecar rules of whatever its
name resembles. It is a read-only view: nothing is copied or loaded again.

Both `filename_issues` and `rule_issues` call `matching_filename_rules`. Because of the
index it takes 0.08 s for all 11,360 files of bids-examples (it took 3.2 s before the
index), so working it out twice costs less than keeping the answer would cost in code.

## 6. Reading files

`checks.integrity.integrity_issues(context)` reports a file that cannot be read the way
its type needs. It asks the context's own loaders (so each file is read once) and turns
the coded `ValidationError` they raise into a finding:

| Code | When |
|---|---|
| `EMPTY_FILE` | 0 bytes; for a directory recording, its files add up to 0 (hidden files not counted) |
| `INVALID_JSON_ENCODING` | not UTF-8, or starts with a byte order mark (JSON forbids one) |
| `JSON_INVALID` | does not parse |
| `JSON_NOT_AN_OBJECT` | parses, but is not an object |
| `NIFTI_HEADER_UNREADABLE` | the NIfTI header cannot be read (an empty image gets this AND `EMPTY_FILE`, as in the reference) |
| `TSV_COLUMN_HEADER_DUPLICATE` | two columns with one name |
| `TSV_EMPTY_LINE` | an empty line that is not the last |
| `TSV_EQUAL_ROWS` | a row with a different number of cells than headers |
| `INVALID_GZIP` | a headerless `.tsv.gz` that does not decompress |
| `MULTIPLE_INHERITABLE_FILES` | two sidecars at one level apply equally well (reported on the first) |

The JSON files a file inherits from are found once, by `Context.sidecar_files`: this check
reports an ambiguous level, the inheritance check compares the files' values, and
`Context.sidecar` and `Context.sidecar_origins` merge them.

`dataset_integrity_issues(dataset)` reports `MISSING_DATASET_DESCRIPTION`.

When a load fails, the context gives the rules an empty value (no header, no columns, an
empty JSON object), so a broken file is reported here once, not again as a failed check
in every rule that reads it. Tables are read up to `context.TSV_MAX_ROWS` rows (1000, the
reference's `--max-rows` default).

## 7. The schema's rules

### 7.1 How a rule is applied

Every rule with selectors has the same shape: when every selector holds, each payload
says what must then be true.

```yaml
ReadmeFileSmall:            # rules.checks.general.ReadmeFileSmall
  issue: {code: README_FILE_SMALL, level: warning, message: "The recommended file ..."}
  selectors: [match(path, '^/README')]
  checks: [size > 150]
```

`checks.rules.rule_issues(context)` evaluates each rule's selectors (stopping at the
first that is not true) and hands each payload to its handler, in the rule's own order,
from `checks.rules.PAYLOAD_HANDLERS`:

| Payload | Handler | Rule groups |
|---|---|---|
| `checks` | `checks.expressions.check_issues` | `rules.checks` |
| `columns`, `initial_columns`, `index_columns` | `checks.tables.column_issues`, `initial_column_issues`, `index_column_issues` | `rules.tabular_data` |
| `fields` | `checks.fields.field_issues` | `rules.sidecars`, `rules.json`, `rules.dataset_metadata` |

`null` follows the schema's documentation (bids-specification `src/schema/README.md`,
"The special value null"): "if an expression (selector or check) evaluates to null, the
null will be interpreted equivalent to false. That is, a null selector will not apply the
current rule, and a null check will fail." An expression that raises counts as `null`, as
in the reference (`_evalCheck` in `applyRules.ts`); it is logged at `DEBUG` level. A
failed `checks` rule reports its own `issue`, with `{...}` placeholders in the message
filled in for the file; a rule without a complete issue reports `CHECK_ERROR`.

### 7.2 Which rules run

`checks.rules.NOT_ENABLED_YET = ('associations', 'ome', 'tiff')`: the parts of the
context not built yet. `names_read_by(rule)` parses a rule's expressions and lists the
context names it reads; a rule reading a held-back name is skipped, because evaluating
it against an empty placeholder would report problems that are not there ("a task scan
needs an events file" would fire on every task scan). With the schema of bidsschematools
1.2.4 (BIDS 1.11.1):

| Group | Rules | Run |
|---|---|---|
| `rules.checks` | 129 | 82 |
| `rules.sidecars` | 174 | 174 |
| `rules.json` | 35 | 35 |
| `rules.dataset_metadata` | 6 | 6 |
| `rules.tabular_data` | 28 | 28 |

(`rules.errors` and the derivative `rules.files` entries also carry selectors but no
payload, so they are skipped in the per-file loop.)

### 7.3 JSON fields

`checks.fields.field_issues` handles the `fields` payload:

* `rules.sidecars` describe a data file's SIDECAR (its JSON files merged by the
  inheritance principle, `context.sidecar`); a missing field is `SIDECAR_KEY_REQUIRED`
  (error) or `SIDECAR_KEY_RECOMMENDED` (warning), on the data file. A `.json` file, and
  `README`-like files, have no sidecar, so these rules skip them.
* `rules.json` and `rules.dataset_metadata` describe one JSON file (`context.json`); a
  missing field is `JSON_KEY_REQUIRED` or `JSON_KEY_RECOMMENDED`.
* A field may carry its own issue (`NO_AUTHORS`, `B0_FIELD_IDENTIFIER_RECOMMENDED` ...),
  used instead, with the field's level as its severity.
* A level addendum "required if `Key` is `Value`" raises the level when the sidecar's
  `Key` is that string. (In the current schema no addendum can take effect: the rule's own
  selectors exclude the triggering value, and for `rules.json` the reference reads the
  addendum's key from the sidecar, which a JSON file does not have. Kept for parity.)
* In a derivative dataset, fields are optional unless the rule selects
  `dataset.dataset_description.DatasetType == "derivative"`.
* A present field's value is checked against its `objects.metadata` definition
  (`checks.values.value_errors`); a wrong value is `JSON_SCHEMA_VALIDATION_ERROR`, on
  the JSON file that holds the key (`Context.sidecar_origins`), and for a sidecar key
  once per dataset, not once per data file inheriting it.

`checks.inheritance.inheritance_issues` warns `SIDECAR_FIELD_OVERRIDE` where a deeper
JSON file gives a field a different value than a JSON file above it (on the deeper file,
once per data file inheriting both). Values are compared by content.

`checks.values.value_errors` implements the JSON Schema the metadata definitions use,
with the behaviour of ajv as the reference configures it: the first failing keyword only
(in ajv's order: `type`, then `enum` and `anyOf`, then the number, string, array and
object keywords), every branch's first error plus `must match a schema in anyOf` when no
alternative fits, ajv's messages (`must be > 0`), and formats SEARCHED rather than
matched (ajv's `RegExp.test`), so a format pattern without `^`/`$` only needs to occur
somewhere in the value.

### 7.4 Tables

`checks.tables` handles the three table payloads, following `schema/tables.ts`:

| Code | When |
|---|---|
| `TSV_COLUMN_MISSING` | a required column is absent (for an initial column, reported by the order check) |
| `TSV_COLUMN_ORDER_INCORRECT` | an initial column is not where the rule puts it |
| `TSV_ADDITIONAL_COLUMNS_NOT_ALLOWED` | a column the rule does not list, where none are allowed |
| `TSV_ADDITIONAL_COLUMNS_MUST_DEFINE` | the same, where extra columns must be defined in the sidecar and this one is not |
| `TSV_ADDITIONAL_COLUMNS_UNDEFINED` | the same, where they are allowed but this one is not defined (warning) |
| `TSV_COLUMN_TYPE_REDEFINED` | the sidecar contradicts the schema's definition of a column (on the sidecar) |
| `TSV_VALUE_INCORRECT_TYPE` | the first value of a column that breaks its type, levels or bounds |
| `TSV_PSEUDO_AGE_DEPRECATED` | `89+` in an `age` column (once) |
| `TSV_INDEX_VALUE_NOT_UNIQUE` | two rows share the index columns' values |

A column's type comes from the schema (`objects.columns`), refined by the sidecar's own
definition of the column (`Format`, `Levels`, `Units`, `Minimum`, `Maximum`), which may
narrow it but not contradict it. `n/a` is always accepted. Column names containing a dot
(`key_resp.rt`, as PsychoPy writes them) work: see section 8.2.

## 8. Changes to the expression language and the context

Both modules are upstream (the expression language is Dan Brady's, PR #71; the context
is Chris Markiewicz's and Dan's). Every change keeps their structure and follows the
schema's documentation or, where it is silent, the reference implementation.

### 8.1 The expression language

The schema's 77 expression test vectors all passed before these changes. They never
compare numbers, never read values loaded from real files, and never test the truth of
an empty array; the schema's rules do all three.

| Behaviour | Before | After | Rules affected |
|---|---|---|---|
| `<`, `<=`, `>`, `>=` | `KeyError` | numbers as numbers, two strings as text, `null` gives `false` | 30 of 129 `rules.checks` (with `**`) |
| `**` | `KeyError` | power | `func.RepetitionTimeMismatch`, `micr.PixelSizeInconsistent` |
| `null + 1`, `null * 2` | `TypeError` | `null` | any arithmetic on a missing field |
| `1 + "a"` | `TypeError` | `"1a"` | |
| `-3 % 2`, `1 / 0` | `1`, `ZeroDivisionError` | `-1`, infinity | |
| truth of `[]`, `{}` | false (Python's rule) | true (the language's rule) | every `!`, `&&`, `\|\|`, selector and check |
| `type("abc")`, `type()` of numpy arrays, tuples, header objects | `"null"` | `"string"`, `"array"`, `"array"`, `"object"` | 29 rules gated on `type(...) != "null"`, which never ran |
| `[1, 2][5]`, `[1, 2][-1]` | `IndexError`, `2` | `null`, `null` | |
| `"x" in record` (an object) | `TypeError` | field present and not null | |
| `".git" in namespace` | inserted a key into the Namespace | tests the keys only | |
| `min`/`max` of TSV cells (`["0.5", "n/a"]`) | `ValueError` | numbers, `n/a` skipped; infinity if none | `events.*` onset checks |
| `length(3)`, `sorted(null)`, `count(null, 1)` | `TypeError`/`AttributeError` | `null` | |
| `intersects("rad", [...])` | `false` (compared characters) | `["rad"]` | |
| `match(42, "4")`, an invalid pattern | `TypeError`, `re.error` | `true`, `null` | |
| an unknown name | `AttributeError` | `null` | |
| an unknown function (`len`) | `'NoneType' object is not callable` | `TypeError: Unknown function 'len'` | `anat.PDT2Echos` (a schema defect) |

New helpers: `truthy` (the language's truth test), `normalize` (numpy and tuples to plain
values), `as_number`, `numeric_values` (replaces `filter_strs`, which dropped numeric
text), and a cached `parse`. `LookupProxy` reads a context attribute once instead of
twice. Measured with the 48 new test vectors: 12 right before, 48 after.

### 8.2 The context

| Change | Why |
|---|---|
| `ValidationError(code, message, line=, location=)` | the upstream TODO ("Add issue structure"): a loader's error carries the code it is reported under |
| `FileContents`, a `dict` with attribute access, holds file contents (JSON, columns) | a bidsschematools `Namespace` reads `"key_resp.rt"` as a path and cannot even list a mapping holding such a key |
| `load_json` raises `INVALID_JSON_ENCODING`, `JSON_INVALID`, `JSON_NOT_AN_OBJECT` | so integrity checks can report them |
| `load_tsv`/`load_tsv_gz` raise `TSV_COLUMN_HEADER_DUPLICATE`, `TSV_EMPTY_LINE`, `TSV_EQUAL_ROWS`, `INVALID_GZIP`; drop a byte order mark; a header with no rows gives empty columns, not none | as the reference; mne-bids writes a byte order mark |
| `Context.read_columns()` (raises) and `Context.columns` (empty on error), up to `TSV_MAX_ROWS` | one place decides how a table is read |
| `Context.sidecar`: cached, empty for a `.json` file, `RepetitionTime` rounded to milliseconds, a broken sidecar skipped rather than fatal | as the reference's `loadSidecar` |
| `walk_back` prefers a candidate with every entity of the source before calling it ambiguous | as the reference's `walkBack` |
| `Context.sidecar_files`: the JSON files a file inherits from, nearest first, found once per file and read by `Context.sidecar`, `Context.sidecar_origins`, the integrity checks and the inheritance checks; `load_sidecar(file)` builds the same merge for one file on its own | four readers each searched the tree again (1.7 s of a 30 s run on bids-examples; 0.6 s now) |
| `Context.sidecar_origins` | where each sidecar key comes from, for value findings; kept only as long as the file's context |
| `Context.json` empty and `Context.nifti_header` `None` when unreadable | the rule sees "no value" instead of raising |
| `Dataset.dataset_description` defaults `DatasetType` (`derivative` with `GeneratedBy`, else `raw`) and is empty when missing | rules selecting `DatasetType == "raw"` otherwise skip every dataset leaving it out |
| `Dataset.checked_sidecar_values` | so a wrong value in a shared sidecar is reported once; the reference keeps the same set on its dataset (`sidecarKeyValidated`) |
| `datatype_to_modality` returns `None` for `phenotype` | it raised `KeyError` |
| `find_datatypes` tests `datatypes.keys()` | `".git" in namespace` inserted a key into the shared, cached schema, and every later context failed |
| `exists()` resolves paths by hand (`tree_contains`) | a leading `/` was never found (so `DUPLICATE_FILES` could not fire) and a `bids::` URI raised |

## 9. Comparison with the reference validator

### 9.1 Method

Both validators were run on the same datasets and their findings compared by
`(code, location)`. Reference: bids-validator 3.0.2 (Deno), schema 1.2.7. This package:
bidsschematools 1.2.4. The scripts are not part of the repository.

### 9.2 Results

**All 84 bids-examples datasets** (at the submodule commit) with a
`dataset_description.json`:

| | Findings |
|---|---|
| reported by both | 141,420 |
| only by the reference | 1,038 |
| only here | 475 |
| crashes | 0 |

Every one of the 1,513 differences has a known cause (9.3).

**A real multimodal dataset** (MRI, fieldmaps, DWI, PET, MEG, EEG, MRS, physiology,
written by BIDS Manager): 50 findings by both, 0 only by the reference, 7 only here (all
explained in 9.3). The reference CRASHES on the full dataset (section 10); the comparison
used a copy without the eye-tracking files.

**One dataset per test case** (59, built from the unit tests): 54 identical; the other 5
are explained in 9.3.

**Speed**: all 84 bids-examples datasets in 27 to 28 s here and 33 s for the reference,
run one after the other on the same machine (2026-11-09). Indexing the filename rules
(section 5) took this package from 32 s to 27 s.

### 9.3 Every difference, and why

Only in the reference:

| Code | Count | Why |
|---|---|---|
| `EVENTS_TSV_MISSING`, `*_CHANNEL_COUNT_MISMATCH`, `MISSING_MAGNITUDE1_FILE`, `REQUIRED_COORDSYSTEM` | 984 | rules reading `associations`: held back until issue #82 |
| `HED_ERROR` | 32 | HED validation is not part of this package yet |
| `SIDECAR_WITHOUT_DATAFILE` | 12 | needs to know which JSON files any rule used, which comes with associations |
| `SIDECAR_FIELD_OVERRIDE` | 6 | the reference compares objects with JavaScript's `!==`, by reference, so the same object written at two levels is reported; here it is compared by content |
| `NOT_INCLUDED` on `sub-*/figures/` | 4 | a reference defect: `figures/` is in that dataset's `.bidsignore`, but the reference tests a folder's path without its trailing `/`, so folder-only patterns never match folders |

Only here:

| Code | Count | Why |
|---|---|---|
| `B0_FIELD_SOURCE_RECOMMENDED`, `SIDECAR_KEY_*` for `AnatomicalImage`, `NonlinearGradientCorrection`, `AnatomicalLandmarkCoordinates` | 423 | a reference defect: these rules select on `dataset.datatypes` or `dataset.modalities`, which the reference never fills in the context its rules see, so they can never apply there |
| `JSON_KEY_RECOMMENDED` for `DatasetType` | 51 | a reference defect: it writes its default `DatasetType` into its cached copy of `dataset_description.json`, so the rule checking the file's own content never sees the field missing |
| `MISSING_DATATYPE` | 1 | in the reference's `main` branch, not yet in a release |
| `MRS_NIFTI_CONSISTENCY` | 2 (real dataset) | the reference stops reading a NIfTI header before its extensions, so it never sees the NIfTI-MRS metadata and never runs this rule |
| `DUPLICATE_FILES` | (test cases) | a reference defect: its `exists()` cannot find a path starting with `/`, so this rule can never fire there |
| `SAMPLES_TSV_MISSING` | (test cases) | the `dataset.modalities` defect above |

The reference's 3.0.2 release also still reports `DATATYPE_MISMATCH` for a `.json` in
another datatype's folder; its `main` branch no longer does, and neither does this
package.

## 10. Defects found in other projects

Found while building and comparing; reported here, not fixed (except where this package
needed to work around them).

| Where | Defect |
|---|---|
| bids-validator (reference) | crashes (`Cannot read properties of undefined (reading 'path')`) on an eye-tracking dataset without an associated events file, while filling the placeholder `{associations.events.path}` of an issue message |
| bids-validator | `exists()` never finds a path starting with `/`, so `DUPLICATE_FILES` cannot fire |
| bids-validator | `dataset.datatypes` and `dataset.modalities` are never filled for the rules, so seven rules can never apply: `checks.dataset.SamplesTSVMissing`, `json.meg.MEGCoordsystemAnatomicalMRI`, `sidecars.meg.MEGwithEEG`, `sidecars.mri.PETMRISequenceSpecifics`, `sidecars.mri.MRIAnatomicalLandmarks`, `sidecars.mri.MRIEchoPlanarImagingAndB0FieldSource`, `sidecars.mrs.MRSConditionalAnatomicalImage` |
| bids-validator | the `DatasetType` default is written into the cached `dataset_description.json`, hiding the missing field |
| bids-validator | `.bidsignore` folder patterns (`figures/`) are not applied to the folders themselves |
| bids-validator | `SIDECAR_FIELD_OVERRIDE` compares objects by reference |
| bidsschematools `Namespace` | `".git" in namespace` inserts an empty key (worked around: `.keys()`) |
| bidsschematools `Namespace` | a key with a dot cannot be held at all (worked around: `FileContents`) |
| BIDS schema `rules.checks.anat.PDT2Echos` | uses `len(...)`, not the language's `length(...)`; the check always fails where it applies |
| BIDS schema `rules.checks.mrs.MRSNiftiConsistency` | compares `SpectrometerFrequency` exactly; the NIfTI-MRS header holds a 32-bit float (`123.26260375976562` against `123.262604`), so it fires on float noise |
| BIDS schema, field level addenda | none can take effect in the current schema (section 7.3) |

## 11. Adding a check

* A new check on each file: write a function `Context -> list[Issue]` in the module that
  matches how it works (or a new one), and add it to `checks.FILE_CHECKS`. On each
  folder: `checks.FOLDER_CHECKS`. On the dataset as a whole: `Dataset -> list[Issue]`
  in `checks.DATASET_CHECKS`.
* Its codes: if the schema defines one, read it with `IssueDefinition.from_schema`;
  otherwise write it out at the top of the module as
  `CODE = IssueDefinition('CODE', Severity..., 'reason')`, with the reference
  validator's severity and reason when it has the code. `tests/checks/test_codes.py`
  fails if the code is defined anywhere else too.
* A new payload kind in the schema: write a handler `(path, rule, context) -> list[Issue]`
  in its own module, and add it to `checks.rules.PAYLOAD_HANDLERS`.
* Something worked out from the schema alone, and needed for every file: decorate the
  function with `checks.schema_cache.once_per_schema`.
* When associations exist (#82): remove `'associations'` from
  `checks.rules.NOT_ENABLED_YET`; 45 more `rules.checks` rules then run (two more wait for
  `ome` and `tiff`).

## 12. Tests

| File | Tests | What they pin |
|---|---|---|
| `tests/checks/test_codes.py` | 11 | where every code is defined: once, beside its checks, or in the schema |
| `tests/checks/test_walk.py` | 22 | ignores, `.bidsignore`, recordings, opaque and derivative folders, order, subjects |
| `tests/checks/test_filename_rules.py` | 8 | rules read into plain values, identification by suffix, path and stem, the folder's rule preferred, derivative rules, the index against a full scan |
| `tests/checks/test_filenames.py` | 36 | every filename code, folders, inheritable files, case, `hide_unused_name_parts`, recordings, derivatives |
| `tests/checks/test_integrity.py` | 21 | every integrity code, readable files staying quiet, sidecar ambiguity |
| `tests/checks/test_rules.py` | 38 | the gate, payload order, null and error semantics, a failing and a passing dataset per sample rule |
| `tests/checks/test_fields.py` | 11 | missing fields, a field's own issue, derivatives, addenda, values reported once where written, and the overrides of `checks.inheritance` |
| `tests/checks/test_tables.py` | 17 | every table code, `n/a`, levels, bounds, redefinition, dotted column names |
| `tests/checks/test_values.py` | 32 | each JSON Schema keyword with ajv's messages, `anyOf`, format search, JSON equality |
| `tests/test_expression_language.py` | 145 | the schema's 77 vectors, 48 more behaviours, numpy and tuple values |
| `tests/test_context.py` | 41 | upstream's, plus the context changes above |
| `tests/checks/test_collect_issues.py`, `tests/test_main.py`, `tests/test_issues.py`, `tests/checks/test_schema_cache.py` | 6, 8, 11, 1 | the order, folders and files getting their own checks, one walk equals the checks apart, one inheritance search per file, the CLI, the data model, the schema cache |

`tests/helpers.py` holds the small dataset builders they share (`write`, `build`,
`clean_dataset` (a dataset both validators find clean), `nifti`, `gzipped`, and
`issues_of`/`findings`, which run some checks or all of them).

664 pass with the bids-examples data (1 skipped: the MRS data needs Git LFS); 635 pass
and 30 skip without it. `ruff check`, `ruff format`, `codespell` and
`mypy --python-version 3.13 src tests` are clean.

## 13. Module reference

| Module | Public names |
|---|---|
| `checks` | `collect_issues(tree, schema, *, dataset_checks, folder_checks, file_checks)`, `DATASET_CHECKS`, `FOLDER_CHECKS`, `FILE_CHECKS` |
| `issues` | `Issue`, `IssueDefinition` (`from_schema`, `make_issue`), `Severity` (`from_level`), `DatasetIssues` |
| `checks.walk` | `iter_contexts(dataset, ignore=None)`, `build_ignore(tree)`, `is_plain_folder(context)`, `DEFAULT_IGNORES`, `PRUNED`, `BIDSIGNORE`, `DERIVATIVES_DIR` |
| `checks.filename_rules` | `matching_filename_rules(context)`, `hide_unused_name_parts(context, rules)`, `all_filename_rules(schema)`, `FilenameRule` |
| `checks.schema_cache` | `once_per_schema` |
| `checks.filenames` | `filename_issues(context)`, `folder_issues(context)`, `SIDECAR_EXTENSIONS`, and the codes of section 3 |
| `checks.integrity` | `integrity_issues(context)`, `dataset_integrity_issues(dataset)`, `LOADER_ERRORS`, `LOADER_ERRORS_IN_SCHEMA`, and the codes of section 3 |
| `checks.rules` | `rule_issues(context)`, `apply_rule(path, rule, context)`, `runnable_rules(schema)`, `names_read_by(rule)`, `PAYLOAD_HANDLERS`, `NOT_ENABLED_YET`, `PreparedRule` |
| `checks.expressions` | `check_issues(path, rule, context)`, `evaluate_or_null(expression, context, path)`, `CHECK_ERROR` |
| `checks.inheritance` | `inheritance_issues(context)`, `SIDECAR_FIELD_OVERRIDE` |
| `checks.fields` | `field_issues(path, rule, context)`, and the codes of section 3 |
| `checks.tables` | `column_issues`, `initial_column_issues`, `index_column_issues` (all `(path, rule, context)`), `AllowedValues`, and the codes of section 3 |
| `checks.values` | `value_errors(value, definition, formats)`, `json_equal(a, b)` |
| `context` (new or changed) | `ValidationError`, `FileContents`, `TSV_MAX_ROWS`, `load_json`, `load_tsv`, `load_tsv_gz`, `tree_contains`, `Context.read_columns`, `Context.columns`, `Context.sidecar_files`, `Context.sidecar_origins`, `Context.sidecar`, `Context.json`, `Context.nifti_header`, `Dataset.dataset_description`, `Dataset.checked_sidecar_values` |
| `expression_language` (new or changed) | `truthy`, `normalize`, `as_number`, `numeric_values`, `parse`, `bin_ops`, `right_ops`, `evaluate` |
