.PHONY : main
main :
	@echo "Targets:"
	@echo "    test-unit"
	@echo "    test-integ"
	@echo "    package"

.PHONY : test-unit
test-unit :
	tox -- test/unit/*.py

.PHONY : test-integ
test-integ :
	tox -- test/integration/*py

.PHONY : package
package :
	python2 setup.py bdist_wheel
	python3 setup.py sdist bdist_wheel
	@echo ""
	@echo "Packages:"
	@find dist -type file

.PHONY : clean
clean :
	rm -rf build dist *.egg-info .pytest_cache
