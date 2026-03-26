# Project Name

EasyWoS

Project which helps users migrate apps from x86-64 to windows on arm64 runs on Qualcomm® *\<Snapdragon X Elite\>*.

## Branches

**main**: Primary development branch. Contributors should develop submissions based on this branch, and submit pull requests to this branch.

## Requirements
Only docker is required, and all the dependent software are listed in the dockerfile, and we package them into a tar file. So you can load it from the <xxx.tar> in the release page.

### load docker image to your local PC
```bash
// You can find the xxx.tar in release page
docker load -i <xxx.tar>
```

### start the docker container
```bash
# -v <host volume path>:<container volume path>
# use docker images command to find your <image-id>
# the name easywos-container can be replaced with anything you like
docker run -itd -p 8888:8888 -v /local/mnt/workspace/zenghao/workspace:/app/workspace --name easywos-container <image-id>
```

## Development

How to develop new features/fixes for the software. Maybe different than "usage". Also provide details on how to contribute via a [CONTRIBUTING.md file](CONTRIBUTING.md).

## Getting in Contact

How to contact maintainers. E.g. GitHub Issues, GitHub Discussions could be indicated for many cases. However a mail list or list of Maintainer e-mails could be shared for other types of discussions. E.g.

* [Report an Issue on GitHub](../../issues)
* [Open a Discussion on GitHub](../../discussions)
* [E-mail us](mailto:haozen@qti.qualcomm.com) for general questions

## License

*\<EasyWoS with BSD-3-clause License\>*

*\<EasyWoS\>* is licensed under the [BSD-3-clause License](https://spdx.org/licenses/BSD-3-Clause.html). See [LICENSE.txt](LICENSE.txt) for the full license text.
