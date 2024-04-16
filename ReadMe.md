
# Debug Extraction

The Debug extraction scripts are used to export [DWARF Standard](https://dwarfstd.org)  information contained in the debug sections of en ELF file into a easily readable JSON format.
The format greatly simplifies the structure of the debug information and only a subset of the information present in the debug section is exported. The exported information is intended to be used to parse information provided to or from the application software in other programming languages, like sending information encapsulated in a structure to the application or parsing data provided from the application on another system.

## Usage

The debug extraction can be performed using

```$ python DebugExtraction.py local <elf-file.elf> --all```

where `<elf-file.elf>` is the path to the ELF file of which the debug information is to be extracted. Depending on the information desired to be extracted, three options are available: Exporting [all debug information](#exporting-all-debug-information), exporting all debug information of [specific type classes](#exporting-debug-information-of-specific-type-classes), or exporting only [specific types by their name](#exporting-specific-types-by-their-names).

### Exporting All Debug Information

All globally defined debug information can be exported with the `-a` or `--all` flag:

```$ python DebugExtraction.py local <elf-file.elf> --all```

When the `-a` or `--all` flag is used, all base types, enumerations, classes, structs, unions, subroutines, typedefs and variables will be exported. Some debug types may be filtered due to additional options, see [Additional Notes on Exporting](#additional-notes-on-exporting).
Note that the `--all` flag is incompatible with the `--class` and `--type` options.

### Exporting Debug information of Specific Type Classes

Specific types of a specific class can be exported with the `-c` or `--class` flag:

```$ python DebugExtraction.py local <elf-file.elf> --class <type-class-1> <type-class-2> ...``` or

```$ python DebugExtraction.py local <elf-file.elf> --class <type-class-1> --class <type-class-2> ...```

Type classes that can be exported are:
* `BaseType`: Base types such as `int`, `unsigned char` or `float`
* `UnspecifiedType`: Unspecified type such as `void`
* `ClassType`: Classes
* `EnumerationType`: Enumerations
* `StructureType`: Structs
* `SubroutineType`: Subroutine prototypes
* `TypeDefType`: Type definitions (aliases of other types)
* `UnionType`: Unions
* `Variable`: Variables

For example, to export all structs and enums, use the command

```$ python DebugExtraction.py local <elf-file.elf> --class StructureType EnumerationType```

Some debug types may be filtered due to additional options, see [Additional Notes on Exporting](#additional-notes-on-exporting).
Note that the `--class` flag is incompatible with the `--all` and `--type` options.

### Exporting Specific Types by their Names

Specific types can be exported with the `-t` or `--type` flag:

```$ python DebugExtraction.py local <elf-file.elf> --type <type1> <type2> ...``` or

```$ python DebugExtraction.py local <elf-file.elf> --type <type1> --type <type2> ...```

For example, to export a type named `my_class`, use:

```$ python DebugExtraction.py local <elf-file.elf> --type my_class```

If the ELF debug information contains multiple types with the same name, only the first match will be exported.
Some debug types may be filtered due to additional options, see [Additional Notes on Exporting](#additional-notes-on-exporting).
Note that the `--type` flag is incompatible with the `--all` and `--class` options.

### Exporting Dependencies

In order to provide the full debug information, the tool also searches for dependencies of the types to be exported and exports them as well. For example, if a structure is selected to be exported and the structure contains member which is an enumeration, that enumeration will also be exported. By default only dependencies of type class, enumeration, structure, subroutine, union and variable are exported as individual entries.

Additionally, the list of types to be exported is filtered according to some criteria:
* Incomplete type definitions (like external variables) are replaced with their completed type before they are exported. If no completed type is found, they are not exported.
* Unless explicitly stated, unnamed types are not exported.
* Typedefs that refer to an unnamed type that is exported will not be exported. The unnamed type will instead be exported with the name of the typedef, as long as only one typedef refers to the type.
* Duplicate types are only exported once.
Statistics for all applied filters can be read from the program output.

After exporting the types to the output file, the exported representations will be validated and warnings will be issued for the following cases:
* Duplicate `"name"` properies of root-level entries,
* Properties with a `null` value and
* Entries with a `"mapping"` property, which is not represented at the root-level.

### Exporting Comments

Additional to the attributes of a type, it is useful in some cases to export some comments associated with type definitions. Comment exporting can be enabled using the `--export-comments` flag. As comments are often discarded during compilation, they cannot be extracted from the ELF file and have to be taken from the source code instead. The Comment Extraction takes the type location information from the ELF file and extracts the comments from the corresponding location in the source file. Thus, it is imperative that source files are not modified after the ELF file was compiled. A warning will be issued for every source file that was modified since the ELF file was compiled, but the comment exporter will still attempt to export the comments from the file.

Depending on the tool chain, the individual source files may be compiled relative to a build folder and the computed file path may not reflect the actual path of the file. In such a case, the `--source-path-subst` flag can be used to substitute elements of the file path. For example, it the source files are located in a folder named `My_Project` and build in `My_Project/build`, the flag can be used as follows:

```$ python DebugExtraction.py local <elf-file.elf> --export-comments --source-path-subst My_Project/build/ My_Project/```

Currently, comment exporting is only supported for `C` and `C++`. For details on how comments are exported, see [Output file format](#output-file-format)

In order to export a comment, the tool searches for the closest comment before and after the declaration. If the closest comment before the declaration is on the same line as the declaration, it is exported. If the closest comment before the declaration is not on the same line, ot is only exported if the line of the beginning of the comment consists only of whitespace characters before the comment and if all characters between the end of the comment and the line of the declaration are whitespace characters. The closest comment after the declaration is only exported if it is either on the same line as the declaration, or on the following line with only whitespace characters before the start of the comment.

### Specifying an Output File

A output file can be specified with the `-o <output file>.json` or `--output <output file>.json` flag. By default, the exported type descriptions will be exported into `export.json`.

### Additional Notes on Exporting

To get a detailed options for running the debug extraction, use the command:
> python DebugExtraction.py --help

## Exporting from GitHub

The script also supports extracting debug information directly from a GitHub repository, without having to download it first. To export the debug information from a GitHub repo, use:

```$ python DebugExtraction.py github <repository> <elf-file.elf> ...```

Where `<repository>` is the name of the repository in the format `OWNER/REPOSITORY` and `<elf-file.elf>` is the name of the ELF file relative to the root of the repository. To export using the information from a specific branch, use the `--branch <branch-name>` option.

If the ELF file is not located in the repository, but present as an artifact generated using GitHub Actions. In this case, use the `--from-artifact <Action-Name> <Artifact-Name>` option. In this case, the ELF file will be extracted from the latest successful run of the Action with the file name provided in `<elf-file.elf>`. Note that `--auth-token-file` option is required to use this option. When exporting debug information with comments using an ELF file built from an artifact, the `--source-path-subst` can be useful to remove the build directory of the GitHub action. For example, use `--source-path-subst /home/runner/work/<REPOSITORY>/<REPOSITORY>/ ""`.

### Authentication

In order to download files from GitHub, the user must provide authentication information. Without any further authentication options, the user will be prompted for their username and password. Alternatively, the user can use the `--auth-token-file <user-token-file>` option, where `<user-token-file>` is a file containing a Github [Personal Access Token](https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api). Such tokens can be created [here](https://github.com/settings/personal-access-tokens/new). The token must have at least read access for Actions, Commit statuses and Contents.

## Output file format

Invoking `DebugExtraction.py` creates a `JSON` file with the extracted Debug information from the given `ELF` file. The name of the output file can be passed with the `--output path/to/output/file.json` option. The filename defaults to `export.json` if the option is not specified.

The `JSON` file is structured as a JSON Array containing a JSON Object for every exported type. The exported types are based on the DWARF Standard Debug TAGs and represent a subset thereof. Currently, the following types and objects are supported:

* [Base](#base-type)
* [Unspecified](#unspecifed-type)
* [Typedef](#typedef)
* [Structure](#structure-union-and-class)
* [Union](#structure-union-and-class)
* [Class](#structure-union-and-class)
* [Enumeration](#enumeration)
* [Pointer](#pointer-or-reference)
* [Reference](#pointer-or-reference)
* [Array](#array)
* [Subroutine](#subroutine)
* [Variable](#variable)

Only the types selected using the scripts arguments are exported. All exported types contain at least the following properties (provided they can be extracted from the given debug information):
* `"datatype"`: A string used to determine the kind of debug information the JSON object represents. A value of, `"typedef"`, `"struct"`, `"union"`, `"class"`, `"enumeration"`, `"pointer"`, `"reference"`, `"array"`, `"subroutine"` or `"variable"` indicate the corresponding type, respectively. Any other value indicates a Basic type. Possible values are basic types can be found [Base Type](#base-type).
* `"name"`: A string providing a name for the exported type. This property is only exported if the corresponding debug type was named. For unnamed types, the name given to a 'typedef' will be used as the property, as long as only one typedef refers to the object. Otherwise, the `"name"` property may be omitted or may be set to `null`. While the names are intended to be unique, it is not guaranteed that they are. If, for example, a struct and a variable were given the same name in the source code, they have the same name in the debug information and thus they have the same `"name"` property. Any duplicate names in lowest-level entries will be reported in the log-file.
All lowest-level entries are guaranteed to have a non-null `"name"` property if the `--include-unnamed` option is not specified.

Other common properties are the following:
* `"datawidth"`: An integer indicating the the number of bytes required to store the underlying type.
* `"type"`: A JSON object representing the underlying type  of the debug information. A type is used when the underlying type is not already exported at the lowest (root) level, which is typically the case for unnamed types like anonymous enumerations, structures and unions or unnamed subroutines.
* `"mapping"`: A string contaning the `"name"` of another debug information entry represented at the root level. A mapping is used to represent nested information, for example if a structure contains another structure or an enumeration.

If the `--export-comments` flag is used, types may have the following propteries:

The following sections contain more detailed descriptions for all debug information types.
* `"comment"`: If only one comment (either before or after) is found, the comment will be exported as a string in the `"comment"` property.
* `"commentBefore"` and `"commentAfter"`: If a comments are found before and after the declaration of the type, they are exported as a string into `"commentBefore"` and `"commentAfter"`, respectively. It is up to the user to determine which of the two comments is actually useful.

### Base Type

A base type represents a fundamental data structure of the language. A root-level entry has the following properties:
* `"datatype"` : A string representing the basic data type as described below.
* `"name"` _(Optional)_: A string providing a name for the data type.
* `"datawidth"`: An integer or null, representing the width in bytes of the data type.

A nested entry has the following properties:
* `"datatype"` _(Optional)_: A string representing the basic data type as described below.
* `"datawidth"`: An integer or null, representing the width in bytes of the data type.

For example, in `C`-Code written for a 32-bit architecture, a `long int` is represented in the exported debug information as:
```
{
  "datatype": "int",
  "name": "long int",
  "datawidth": 4
}
```
The entry describes an `"int"` (integer) data type, with a name `"long int"`, of which an instance occupies 4 Bytes.

The most common values for `"datatype"` are:
* `"void"`: A void (empty) type,
* `"boolean"`: A boolean value,
* `"char"`: A signed character,
* `"uchar"`: An unsigned character,
* `"int"`: A signed integer,
* `"uint"`: An unsigned integer and
* `"float"`: A floating point number.

Other, less common values are `"address"`, `"complex float"`, `"imaginary float"`, `"packed decimal"`, `"numerical string"`, `"edited"`, `"fixed"`, `"ufixed"`, `"decimal float"`, `"UTF"`, `"UCS"` and `"ASCII"`. Note that they only represent a subset of possible DWARF types. If the type is any other DWARF type or if the encoding of the base type is unknown, the `"datatype"` is set to `"Unknown"`.

### Unspecified Type

An unspecified type entry has the following properties:
* `"datatype": "unspecified"`
* `"name"`: A string providing a name for the unspecified data type.

### Typedef

A typedef represents an alias for another type. A root-level entry has the following properties:
* `"datatype": "typedef"`
* `"name"`: A string providing a name for the typedef.
* `"type"` or `"mapping"`: If the type the typedef refers to has an entry at the root level of the output file, the typedef entry contains a `"mapping"` property with a string as a value that serves as a reference to the name of the type. Otherwise, if the type the typedef refers to does not have an entry at the root level, the entry has a `"type"` property containing a JSON Object which represents the underlying type.

A nested entry has the following properties:
* `"datatype": "typedef"`
* `"mapping"`: A string referring to the name of type entry located at the root level, which describes the type of the typedef.

Note that if a typedef is not selected for export, it may be bypassed while exporting and not show up at all. For example, if the type of a Variable 'A' is a typedef 'B', which in turn refers to basic type 'C', the representation A -> B -> C may be replaced with A -> C, to that the type of A is directly shown as basic type 'C' to make the debug representation smaller.

### Structure, Union and Class

A structure, union or class represent a grouping of member information. The debug information for all three of them is very similar.

A root-level or a nested unnamed (anonymous) entry has the following properties:
* `"datatype": "struct"`, `"union"` or `"class"` for a structure, union or class, respectively.
* `"datawidth"`_(Optional)_: An integer representing the width in bytes of the data type.
* `"name"`_(Optional)_: A string providing a name for the structure, member or union.
* `"members"`: A JSON array of Members. Members debug entries are exported as described [Member](#Member)

A named nested entry has the following properties:
* `"datatype": "struct"`, `"union"` or `"class"` for a structure, union or class, respectively.
* `"datawidth"`_(Optional)_: An integer representing the width in bytes of the data type.
* `"mapping"`: A string providing a name for the structure, member or union which contains a debug entry at the root level.

Note that an unnamed (anonymous) entry will be represented the same way as a root-level entry, even if it is nested.

#### Member

A Member entry has the following properties:
* `"identifer"`_(Optional)_: A string providing an identifier for the member. Only present if the member is named.
* `"mapping"`_(Optional)_: If the type of the member is exported at the root level, the `"mapping"` property contains a string corresponding the name of the type.
* `"datawidth"`_(Optional)_: An integer representing the width in bytes of the data type. Only present if the size of the member is known.
* `"bit_size"`_(Optional)_: Number of bits the member occupies. Only used if the member occupies a non-integer amount of bytes.
* `"byte_offset"`_(Optional)_: If the member has a known offset in memory relative to the location of the containing structure, union or class, the offset in bytes is given as an integer in this property.
* `"bit_offset"`_(Optional)_: If the member has a known bit offset in memory relative to the location of the containing structure, union or class, the offset in bit is given as an integer in this property. Note that both the `"byte_offset"` and the `"bit_offset"` property have to be considered to compute the correct location of the member. The `"bit_offset"` property is omitted if its value is 0.

If the member has a type which is not exported at the root level, the type will be directly exported at the same level into the member (not nested). The kind of the type can be determined with the `"datatype"` property is such a case. If the member has no type, neither the `"mapping"` nor the `"datatype"` property will be present.

### Enumeration

A root-level enumeration entry has the following properties:
* `"datatype": "enumeration"`
* `"datawidth"`_(Optional)_: An integer representing the width in bytes.
* `"name"`_(Optional)_: A string providing a name for the enumeration.
* `"encoding"`_(Optional)_: A providing the encoding type of the enumeration. Can be any of the encodings described in [Base Type](#base-type).
* `"type"`_(Optional)_: A JSON Object representing the underlying type of the enumeration. Only present if the enumeration has an associated type and the `"encoding"` or `"datawidth"` property are absent. If the `"datawidth"` property is present, it takes precedence over the data width of the `"type"`.
* `"enumerators"`: A JSON array of Enumerators. Enumerator debug entries are exported as described [Enumerator](#Enumerator)

A nested entry has the following properties:
* `"datatype": "enumeration"`
* `"datawidth"`_(Optional)_: An integer representing the width in bytes.
* `"mapping"`_(Optional)_: A string referencing the name of a root-level entry which contains the full debug entry.

Note that values in enumerators are not guaranteed to be unique.

#### Enumerator

An Enumerator JSON Object has the following properties:
* `"value"`: An integer value of the enumerator
* `"representation"`: A string used as a representation of the identifier

### Pointer or Reference

A pointer or reference entry has the following properties:
* `"datatype": "pointer"` or `"reference"` for a pointer or reference, respectively.
* `"datawidth"`: An integer representing the width in bytes used to hold the address of the referenced type.
* `"type"`_(Optional)_: A JSON object containing the debug information of the type. If the type is expanded at root level, it contains a `"mapping"` to the type, otherwise it contains the type itself.

If the pointer or reference points to a specific type, the entry has a `"type"` property. Otherwise, the type is assumed to be unknown or 'void'. Note that the type will be recursively expanded if it's a typedef, until the type is either represented at the root level (in which case a `"mapping"` property is present), or referenced type is not typedef.

### Array

An array entry has the following properties:
* `"datatype": "array"`.
* `"dimensions"`: A JSON Array containing integer values representing the dimensions of the array. If a dimension is unknown, it will be represented by a `null` entry.
* `"stride"`_(Optional)_: If two consecutive array elements are spaced further apart than the byte size of the underlying type, this property contains an integer value representing the spacing between the array elements in bytes.
* `"type"`: A JSON object containing a representation of the type of the array entries.

### Subroutine

An subroutine entry has the following properties:
* `"datatype": "subroutine"`.
* `"name"`_(Optional)_: A string providing a name for the subroutine. Only present if the subroutine is named.
* `"type"`_(Optional)_: A JSON object containing a representation of the return type of the subroutine. If the `"type"` property is not present, the return type is assumed to be unknown or void.
* `"parameters"`: A JSON Array containing the representations of the [parameters](#formal-parameter) of the subroutine.

#### Formal Parameter

An subroutine entry has the following properties:
* `"name"`_(Optional)_: A string providing a name for the parameter. Only present if the parameter is named.
* `"type"`_(Optional)_: A JSON object containing a representation of the type of the parameter. If the `"type"` property is not present, the type is assumed to be unknown.

### Variable

An subroutine entry has the following properties:
* `"datatype": "variable"`.
* `"name"`_(Optional)_: A string providing the name of the variable. Only present if the variable is named.
* `"type"`_(Optional)_: A JSON object containing a representation of the type of the variable. If the `"type"` property is not present, the type is assumed to be unknown.
* `"location"`_(Optional)_: An integer representing the address of the variable. Only present if the location of the variable is known.
* `"physical_location"`_(Optional)_: An integer representing the load address of the variable. Only present if the location of the variable is known.
