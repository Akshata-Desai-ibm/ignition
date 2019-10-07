# Release

The following steps detail how an Ignition release is produced. This may only be performed by a user with admin rights to this Git repository and the Pypi repository.

## 1. Setting the Version

1.1 Start by setting the version of the release in `ignition/pkg_info.json` (push this change to Github and let the CI build execute):

```
{
  "version": "<release version number>"
}
```

1.2 Tag the commit with the new version in Git

## 2. Build Python Wheel

Build the python wheel by navigating to the Ignition root directory and executing:

```
python3 setup.py bdist_wheel
```

The whl file is created in `dist/`

## 3. Upload to Pypi

Upload the whl file to pypi using `twine` (note: this command will ask for your pypi repository access credentials)

```
python3 -m twine upload dist/<whl file>.whl
```

## 4. Package the docs

Create a TAR of the docs directory:

```
tar -cvzf ignition-framework-<release version number>-docs.tgz docs/ --transform s/docs/ignition-framework-<release version number>-docs/
```

## 5. Create release on Github

5.1 Navigate to Releases on the Github repository for this project and create a new release.

5.2 Ensure the version tag and title correspond with the version number set in the pkg_info file earlier

5.3 Attach the docs archive to the release

## 6. Generate Release Notes

Release notes are produced by updating the CHANGELOG.md, then copying the section for this version to the description field in the created Github release.

The CHANGELOG is updated using [github-changelog-generator](https://github.com/github-changelog-generator/github-changelog-generator#why-should-i-care)

6.1 Update CHANGELOG.md

```
github_changelog_generator accanto-systems/ignition
```

6.2 Commit the updated CHANGELOG.md

6.3 Copy the section for the newly released version from CHANGELOG.md into the description of the release created on Github

## 7. Set next development version

Set the version of the next development version in `ignition/pkg_info.json` (push this change to Github).

Usually the next dev version should be an minor increment of the previous, with `dev0` added. For example, after releasing 0.1.0 it would be:

```
{
  "version": "0.2.0.dev0"
}
```