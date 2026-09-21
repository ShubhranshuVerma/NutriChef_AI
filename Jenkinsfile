// NutriChef AI - one click on "Build Now" runs the whole project, step by step.
//
// Every stage runs one of the project's own commands, in your project folder,
// with your project's Python. If a stage fails, the next ones do not run and
// the console shows why. Setup steps: README.md, section "Jenkins".

pipeline {
    agent any

    environment {
        // Your project folder on this Mac and the Python inside its .venv.
        PROJECT = "${env.HOME}/NutriChef_AI"
        PY      = "${env.HOME}/NutriChef_AI/.venv/bin/python"
        // Jenkins does not use your terminal's settings, so tell it where docker is.
        PATH    = "/usr/local/bin:/opt/homebrew/bin:${env.PATH}"
    }

    stages {
        stage('Install libraries') {
            steps {
                dir(env.PROJECT) {
                    sh '$PY -m pip install -r requirements.txt -r requirements-dev.txt'
                }
            }
        }

        stage('Build data') {
            steps {
                dir(env.PROJECT) {
                    // --rebuild starts the search index fresh, so recipes are not added twice
                    sh '$PY -m scripts.build_data --rebuild'
                }
            }
        }

        stage('Train ranker') {
            steps {
                dir(env.PROJECT) {
                    sh '$PY -m scripts.train_ranker'
                }
            }
        }

        stage('Check setup') {
            steps {
                dir(env.PROJECT) {
                    sh '$PY -m scripts.check'
                }
            }
        }

        stage('Run tests') {
            steps {
                dir(env.PROJECT) {
                    sh '$PY -m pytest -q'
                }
            }
        }

        stage('Demo meal plan') {
            steps {
                dir(env.PROJECT) {
                    sh '$PY -m scripts.demo plan --days 3'
                }
            }
        }

        stage('Build Docker image') {
            steps {
                dir(env.PROJECT) {
                    sh 'docker compose build'
                }
            }
        }
    }

    post {
        success { echo 'All steps passed.' }
        failure { echo 'A step failed - open the red stage and read its log.' }
    }
}
