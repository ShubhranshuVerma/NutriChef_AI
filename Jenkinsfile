// NutriChef AI - checks every change pushed to GitHub.
//
// Jenkins takes a clean copy of the code from GitHub (not your working folder), then:
//   1. Setup        a fresh .venv with the project's libraries
//   2. Test         the test suite; an HTML report opens in your browser, and the
//                   results also appear on the build's "Tests" page
//   3. Build image  the Docker image, tagged with the build number
//   4. Smoke test   start that image and check that /health answers
//
// Rebuilding the data and the ranker is not part of it (run those two scripts yourself).
// Setup steps: README.md, section "Jenkins".

pipeline {
    agent any

    // Look at GitHub every 5 minutes and build any new commit. "Build Now" works too.
    triggers { pollSCM('H/5 * * * *') }

    environment {
        // The Python 3.11 used to create the .venv. Change this if yours is elsewhere
        // (in a terminal, `pyenv which python` shows the path).
        PYTHON = "${env.HOME}/.pyenv/versions/3.11.8/bin/python3"
        // Jenkins does not use your terminal's settings, so tell it where docker is.
        PATH   = "/usr/local/bin:/opt/homebrew/bin:${env.PATH}"
    }

    stages {
        stage('Setup') {
            steps {
                // The .venv stays in Jenkins' copy between builds, so later installs are quick.
                sh '''
                    $PYTHON -m venv .venv
                    .venv/bin/python -m pip install --quiet --upgrade pip
                    .venv/bin/python -m pip install --quiet -r requirements.txt -r requirements-dev.txt
                '''
            }
        }

        stage('Test') {
            steps {
                // No .env and no data needed: Gemini is a fake in the tests.
                sh '.venv/bin/python -m pytest -q --junitxml=test-results.xml --html=test-report.html --self-contained-html'
            }
            post {
                always {
                    junit 'test-results.xml'
                    // Keep the report with the build (build page -> Build Artifacts) ...
                    archiveArtifacts artifacts: 'test-report.html', allowEmptyArchive: true
                    // ... and open it in your browser now, passed or failed (macOS "open").
                    sh 'open test-report.html || true'
                }
            }
        }

        stage('Build image') {
            steps {
                sh 'docker build -t nutrichef-ai:$BUILD_NUMBER -t nutrichef-ai:latest .'
            }
        }

        stage('Smoke test') {
            steps {
                // Start the new image with no data and no keys, and ask /health from inside
                // the container. No port is opened, so nothing on this Mac can clash with it.
                sh '''
                    docker rm -f nutrichef-smoke 2>/dev/null || true
                    docker run -d --name nutrichef-smoke nutrichef-ai:$BUILD_NUMBER
                    for i in $(seq 1 30); do
                        if docker exec nutrichef-smoke python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read().decode())"; then
                            echo "The new image starts and answers /health."
                            exit 0
                        fi
                        sleep 2
                    done
                    echo "No answer from /health after 60 seconds. The app's log:"
                    docker logs nutrichef-smoke
                    exit 1
                '''
            }
            post {
                always { sh 'docker rm -f nutrichef-smoke 2>/dev/null || true' }
            }
        }
    }

    post {
        success { echo "Build $BUILD_NUMBER passed: tested, image built, image starts." }
        failure { echo 'A stage failed - open the red stage and read its log.' }
    }
}
