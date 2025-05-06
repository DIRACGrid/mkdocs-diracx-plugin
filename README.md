mkdocs plugin to merge the documentation of all the DiracX ecosystem together


Put the following in the mkdocs.yml of diracx

```yaml
plugins:
  - diracx:
      repos:
        - url: https://github.com/DIRACGrid/diracx-charts.git
          branch: mkdoc
          include: 
            - docs
            - diracx
        - url: https://github.com/DIRACGrid/diracx-web.git
          branch: mkdoc
          include: 
            - docs
            - whatever source is needed
```