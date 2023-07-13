# kraken-wrapper

Using the `krakenw` CLI is the recommended method for interacting with the Kraken build system as a user (i.e. as
a developer working on a Kraken-powered project). It serves as a thin wrapper around the `kraken` CLI to add various
quality of life features to building projects with Kraken.


## Responsibilities

The `krakenw` CLI has the following responsibilities that are not coverred by the `kraken` CLI. Under the hood, the
wrapper delegates to the `kraken` CLI that is installed into a dedicated build environment.

* __Lock files__: The `krakenw lock` command creates a `.kraken.lock` file that contains the details of your current
    build environment. Check this file into your repository to ensure that CI or the next developer building the
    project is using the exact same version of the build system as you are. Use `krakenw --upgrade lock` to upgrade
    the dependencies of your build environment.

* __Execute in subdirectories__: The `krakenw` CLI will find the root of your project and pass the relative path to
    it to the `kraken` CLI via the `-p,--project-dir` option. This is a convenience feature such that you don't need
    to manually point to the root of your project when you run `krakenw` inside a subdirectory of your project.

* __Credentials management__: The `krakenw auth` command can be used to associate a hostname with a username and
    password pair. These credentials are used to authenticate with a Python package index when installing dependencies
    when necessary. The same credentials may be read by the Kraken build system to authenticate with the same package
    index when building your project. For more information, see [Credentials management](#credential-management).


## Build script contract

There is an API contract between Kraken build scripts and the wrapper that is based on the `kraken.common.buildscript()`
function. This function is used to declare the build script's dependencies that the wrapper will pick up to build a
Python virtual environment for your build script.

Note that the `buildscript()` function is completely ignored when running your build script directly with the `kraken`
CLI and all dependencies required for your build must already be installed in your Python environment.

```py
from kraken.common import buildscript

buildscript(
    requirements=["kraken-std"]
)

from kraken.std import python

python.mypy()
# ...
```

The way this works is that when Kraken-Wrapper is executed, it will detect the build script and execute it in a way
such that the `buildscript()` function raises a specific exception that contains the information you passed to it. The
wrapper catches this exception and uses the information to build a virtual environment in which your build is then
actually executed. Subsequently, Kraken-Wrapper will invoke the `kraken` CLI in the virtual environment to execute
the build script again, only this time the `buildscript()` function call does nothing.


## Credentials management

  [keyring]: https://github.com/jaraco/keyring

Pip doesn't really have a good way to globally configure credentials for Python package indexes when they are not
configured as an alias in `.piprc` aside from `~/.netrc`. Both of these methods have the drawback that the password
is stored in plain text on disk. Pip does technically support looking up a password from the system keychain using
the [`keyring`][keyring] package, but it doesn't store the username and so will have to ask for it via stdin.

To work around this limitation, kraken-wrapper offers the `auth` command which allows you to configure credentials
where the username is stored in `~/.config/krakenw/config.toml` and the password is stored in the system keychain
(also using the [`keyring`][keyring] package).

    $ krakenw auth example.jfrog.io -u my@email.org
    Password for my@email.org:

> __Important note__: If no backend for the `keyring` package is available, kraken-wrapper will fall back to writing
> the password as plain text into the same configuration file. A corresponding warning will be printed.


## Sub-project support

The `kraken` CLI supports running in a sub project, but requires that you point it to the root of your project using
the `-p,--project-dir` option. The `krakenw` CLI will automatically find the root of your project and pass it to the
`kraken` CLI for you. This means that you can run `krakenw` from anywhere in your project and it will behave as if you
had run it from the root of your project but in the context of the current directory. Relative addresses passed to the
CLI will be considered relative to the Kraken project of the current directory.

For example, if you have a project with the following structure:

    .
    ├── .kraken.py
    └── sub-project
        └── .kraken.py

And you have a task `:t` in the sub-project, you can run it from the root of your project or the sub-project with
the `kraken` CLI like thisL

    (.)           $ kraken run sub-project:t
    (sub-project) $ kraken run t -p ..

And with the `krakenw` CLI like this:

    (.)           $ krakenw run sub-project:t
    (sub-project) $ krakenw run t

If you want to stop `krakenw` from crawling up the directories until it finds the `.git` project's top level directory
and the top-most Kraken build script, you can add `# ::krakenw-root` as a comment to the top of your build script in
a sub-directory. This allows you to effectively treat a sub-directory as a separate Kraken project.
