SHELL := bash

.PHONY: check dist venv test pyinstaller debian deploy

version := $(shell cat VERSION)
architecture := $(shell dpkg-architecture | grep DEB_BUILD_ARCH= | sed 's/[^=]\+=//')

debian_package := rhasspy-g2p-hermes_$(version)_$(architecture)
debian_dir := debian/$(debian_package)

check:
	flake8 rhasspyg2p_hermes/*.py test/*.py
	pylint rhasspyg2p_hermes/*.py test/*.py

venv: phonetisaurus.tar.gz
	rm -rf .venv/
	python3 -m venv .venv
	.venv/bin/pip3 install wheel setuptools
	.venv/bin/pip3 install -r requirements_all.txt
	tar -C .venv -xzvf phonetisaurus.tar.gz

phonetisaurus.tar.gz:
	wget -O "$@" 'https://github.com/synesthesiam/docker-phonetisaurus/releases/download/v2019.1/phonetisaurus-2019-$(architecture).tar.gz'

test:
	coverage run -m unittest test

coverage:
	coverage report -m

dist: sdist debian

sdist:
	python3 setup.py sdist

pyinstaller:
	mkdir -p dist
	pyinstaller -y --workpath pyinstaller/build --distpath pyinstaller/dist rhasspyg2p_hermes.spec
	tar -C pyinstaller/dist -czf dist/rhasspy-g2p-hermes_$(version)_$(architecture).tar.gz rhasspyg2p_hermes/

debian: pyinstaller
	mkdir -p dist
	rm -rf "$(debian_dir)"
	mkdir -p "$(debian_dir)/DEBIAN" "$(debian_dir)/usr/bin" "$(debian_dir)/usr/lib"
	cat debian/DEBIAN/control | version=$(version) architecture=$(architecture) envsubst > "$(debian_dir)/DEBIAN/control"
	cp debian/bin/* "$(debian_dir)/usr/bin/"
	cp -R pyinstaller/dist/rhasspyg2p_hermes "$(debian_dir)/usr/lib/"
	cd debian/ && fakeroot dpkg --build "$(debian_package)"
	mv "debian/$(debian_package).deb" dist/

docker: pyinstaller
	docker build . -t "rhasspy/rhasspy-g2p-hermes:$(version)"

deploy:
	echo "$$DOCKER_PASSWORD" | docker login -u "$$DOCKER_USERNAME" --password-stdin
	docker push rhasspy/rhasspy-g2p-hermes:$(version)
